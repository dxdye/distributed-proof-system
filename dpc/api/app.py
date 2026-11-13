"""HTTP API of the coordination service (component C9; SR-21, SR-23, SR-30).

Reviewers authenticate with a bearer token: the API token issued at
registration, or an access token of a configured identity provider such as
Keycloak (docs/adr/0010). What the API returns to a reviewer is built from the
same fields for real tickets and honeypots; nothing about honeypots, trust
values of others or lease expiry times is exposed (SR-06, SR-23, SR-30).
Public endpoints return aggregates.
"""

# No `from __future__ import annotations`: FastAPI resolves the dependency
# aliases defined inside `create_app` at runtime.
import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from dpc.auth import Authenticator, AuthError, Identity, LocalTokenProvider
from dpc.coord import NOTICE_VERSION, CoordError, Coordinator
from dpc.coord.state import LeaseSt, TicketSt
from dpc.coord.tiers import tier_of
from dpc.tickets.model import QUESTIONS_A, AIAssistance

NOTICE = (
    "Reviews you submit (verdicts, justifications, evidence files) are published "
    "under an open licence together with the reports, and may be used to train "
    "and evaluate AI systems. Your account is pseudonymous: the published audit log "
    "identifies you only by a random id. Do not use your real name as pseudonym if "
    "you do not want to be identifiable. Declare any employment by or commission from "
    "a lab whose submissions you might review."
)

QUESTIONS: dict[str, str] = {
    "fidelity": "Does the formal statement say what the paper claims — no more, no less?",
    "junk_values": "Could junk values (x / 0 = 0, default values, truncated subtraction) "
                   "make the statement weaker than intended?",
    "edge_cases": "Are the edge cases (empty sets, zero, dimension 0 or 1) handled as in "
                  "the paper?",
    "vacuity": "Can all hypotheses be satisfied at the same time, or is the statement "
               "vacuous?",
    "quantifiers": "Are quantifiers, their order and the types of bound variables right?",
}


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterReq(_Req):
    pseudonym: str
    group: Literal["expert", "doctoral", "student", "other"] = "other"
    affiliations: list[str] = []
    notice_acknowledged: bool = False


class AffiliationReq(_Req):
    lab: str


class PreferencesReq(_Req):
    domains: list[str] = []
    tiers: list[Literal["easy", "medium", "hard", "excellence"]] = []


class LeaseReq(_Req):
    set_id: str
    ticket_id: str


class ReviewReq(_Req):
    verdict: Literal["correct", "incorrect"]
    reason: str = ""
    failed: list[Literal["fidelity", "junk_values", "edge_cases", "vacuity",
                         "quantifiers"]] = []
    evidence: str | None = Field(default=None, description="Lean file backing 'incorrect'")
    evidence_kind: Literal["vacuity", "trivialization", "definition_test_counterexample"] | \
        None = None
    ai_used: bool = False
    ai_provider: str | None = None


class ClaimReq(_Req):
    confirmed: bool
    reason: str


class DecideReq(_Req):
    error: bool
    reason: str


def create_app(coord: Coordinator, *, auth: Authenticator | None = None,
               static_dir: Path | None = None, tick_seconds: float | None = 60.0) -> FastAPI:
    """``auth``: sign-in methods (default: the service's own API tokens only).
    ``tick_seconds``: period of lease expiry and honeypot reveals (None: off)."""
    authenticator = auth or Authenticator([LocalTokenProvider(coord.vault)])

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if tick_seconds:
            async def ticker() -> None:
                while True:
                    await asyncio.sleep(tick_seconds)
                    coord.tick()
            task = asyncio.create_task(ticker())
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="Distributed Proof Check", version="0.1.0", lifespan=lifespan)

    def call(fn: Any, *args: Any, **kw: Any) -> Any:
        try:
            return fn(*args, **kw)
        except CoordError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    def identity(authorization: str | None) -> Identity:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        try:
            return authenticator.identify(authorization.removeprefix("Bearer ").strip())
        except AuthError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    def account(ident: Identity) -> str | None:
        rid = ident.subject if ident.local else \
            coord.vault.reviewer_for_identity(ident.provider, ident.subject)
        return rid if rid is not None and rid in coord.state.reviewers else None

    def reviewer(authorization: Annotated[str | None, Header()] = None) -> str:
        ident = identity(authorization)
        rid = account(ident)
        if rid is None:
            raise HTTPException(403, "no reviewer account for this sign-in; register first")
        if ident.maintainer is not None:  # the provider manages the maintainer role
            coord.sync_maintainer(rid, ident.maintainer)
        return rid

    def maintainer(rid: Annotated[str, Depends(reviewer)]) -> str:
        if not coord.state.reviewers[rid].maintainer:
            raise HTTPException(403, "maintainers only")
        return rid

    Rid = Annotated[str, Depends(reviewer)]
    Admin = Annotated[str, Depends(maintainer)]

    def ticket_card(ticket: TicketSt) -> dict[str, Any]:
        """What is shown in a choice set: no counts, no popularity (SR-38)."""
        sub = coord.state.submissions[ticket.submission_id]
        _, expected = coord.lease_duration("review", ticket)
        return {"ticket_id": ticket.ticket_id, "declaration": ticket.view.declaration,
                "decl_kind": ticket.view.decl_kind, "domain": ticket.domain,
                "tier": tier_of(ticket.difficulty),
                "paper": sub.title, "expected_minutes": max(1, round(expected / 60))}

    def lease_view(lease: LeaseSt) -> dict[str, Any]:
        st = coord.state
        ticket = st.tickets[lease.ticket_id]
        sub = st.submissions[ticket.submission_id]
        out: dict[str, Any] = {
            "lease_id": lease.lease_id, "duty": lease.duty, "status": lease.status,
            "extendable": lease.status == "active" and not lease.extended,
            "min_reason_chars": coord.params.min_reason_chars,
            # SR-30: the expected duration, never a countdown or expiry time.
            "expected_minutes": max(1, round(lease.expected_s / 60)),
            "ticket": {
                "ticket_id": ticket.ticket_id, "paper": sub.title, "repo_url": sub.repo_url,
                "commit": sub.commit, "domain": ticket.domain,
                "tier": tier_of(ticket.difficulty),
                "view": ticket.view.model_dump(mode="json"),
                "questions": [{"id": q, "text": QUESTIONS[q]} for q in QUESTIONS_A],
            },
        }
        if lease.duty == "claim" and lease.claim_id is not None:
            claim = st.claims[lease.claim_id]
            review = st.reviews[claim.review_seq]
            out["claim"] = {"claim_id": claim.claim_id, "reason": review.reason,
                            "failed": list(review.failed),
                            "evidence": review.evidence.model_dump() if review.evidence
                            else None}
        return out

    # ------------------------------------------------------------- public
    @app.get("/api/notice")
    def notice() -> dict[str, str]:
        return {"version": NOTICE_VERSION, "text": NOTICE}

    @app.get("/api/stats")
    def stats() -> dict[str, object]:
        with coord.lock:
            return coord.stats()

    @app.get("/api/attention")
    def attention() -> dict[str, float]:
        with coord.lock:
            psi = coord.attention()
            return {coord.state.submissions[s].title: round(v, 3) for s, v in psi.items()}

    @app.get("/api/audit/head")
    def audit_head() -> dict[str, object]:
        with coord.lock:
            head = coord.log.head()
            return {"length": len(coord.log), "head_hash": head.hash if head else None}

    @app.get("/api/auth/config")
    def auth_config() -> dict[str, object]:
        """Sign-in methods the web client may offer."""
        return authenticator.public_config()

    @app.get("/api/auth/session")
    def session(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
        """Whether a credential is valid and already has a reviewer account."""
        if not authorization:
            return {"authenticated": False}
        try:
            ident = identity(authorization)
        except HTTPException as exc:
            return {"authenticated": False, "error": exc.detail}
        return {"authenticated": True, "provider": ident.provider,
                "registered": account(ident) is not None}

    @app.post("/api/register")
    def register(req: RegisterReq,
                 authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
        """With an identity provider's token: links that sign-in to the new
        account. Without: issues an API token (if local tokens are enabled)."""
        if authorization:
            ident = identity(authorization)
            if ident.local or account(ident) is not None:
                raise HTTPException(409, "already registered")
            rid, _ = call(coord.register, req.pseudonym, req.group, req.affiliations,
                          notice_acknowledged=req.notice_acknowledged,
                          identity=(ident.provider, ident.subject))
            if ident.maintainer:
                coord.sync_maintainer(rid, True)
            return {"reviewer_id": rid}
        if not authenticator.local_tokens:
            raise HTTPException(401, "sign in with an identity provider first")
        rid, token = call(coord.register, req.pseudonym, req.group, req.affiliations,
                          notice_acknowledged=req.notice_acknowledged)
        return {"reviewer_id": rid, "token": token}

    # ------------------------------------------------------------ reviewer
    @app.get("/api/me")
    def me(rid: Rid) -> dict[str, Any]:
        with coord.lock:
            st, now = coord.state, coord.now()
            person = st.reviewers[rid]
            domains = sorted({e.domain for e in person.evidence})
            history = []
            for r in st.reviews.values():
                if r.reviewer != rid:
                    continue
                t = st.tickets[r.ticket_id]
                history.append({
                    "declaration": t.view.declaration, "paper": st.submissions[
                        t.submission_id].title, "verdict": "incorrect" if r.incorrect
                    else "correct", "duty": r.duty, "submitted": r.ts.isoformat(),
                    "outcome": t.status if t.status != "open" else None,
                    # Only after the delayed, batched reveal (SR-37):
                    "planted_error": t.honeypot})
            return {
                "reviewer_id": rid, "pseudonym": coord.vault.pseudonym(rid),
                "group": person.group, "maintainer": person.maintainer,
                "roles": {d: sorted(st.roles(rid, d, now)) for d in domains},
                "preferences": {"domains": list(person.pref_domains),
                                "tiers": list(person.pref_tiers)},
                "tiers_open": coord.tiers_open(rid),
                "reliability": round(person.reliability.rate.mean, 3),
                "wip_limit": person.reliability.wip_limit("A"),
                "leases": [lease_view(lease) for lease in st.active_leases(rid)],
                "history": history[::-1][:50],
            }

    @app.put("/api/me/preferences")
    def preferences(req: PreferencesReq, rid: Rid) -> dict[str, bool]:
        call(coord.set_preferences, rid, domains=req.domains, tiers=req.tiers)
        return {"ok": True}

    @app.get("/api/domains")
    def domains(_: Rid) -> list[str]:
        """Domains of the open class-A tickets (names only, no counts)."""
        with coord.lock:
            st = coord.state
            return sorted({t.domain for t in st.tickets.values()
                           if t.ticket_class == "A" and st.is_open(t)})

    @app.post("/api/me/affiliations")
    def affiliation(req: AffiliationReq, rid: Rid) -> dict[str, bool]:
        call(coord.declare_affiliation, rid, req.lab)
        return {"ok": True}

    @app.post("/api/choice-set")
    def choice_set(rid: Rid) -> dict[str, Any]:
        with coord.lock:
            cs = call(coord.choice_set, rid)
            if cs is None:
                return {"set_id": None, "tickets": []}
            return {"set_id": cs.set_id,
                    "tickets": [ticket_card(coord.state.tickets[t]) for t in cs.tickets]}

    @app.post("/api/leases")
    def take(req: LeaseReq, rid: Rid) -> dict[str, Any]:
        with coord.lock:
            return lease_view(call(coord.lease, rid, req.set_id, req.ticket_id))

    @app.post("/api/duties/next")
    def next_duty(rid: Rid) -> dict[str, Any] | None:
        with coord.lock:
            lease = call(coord.next_duty, rid)
            return None if lease is None else lease_view(lease)

    def own(rid: str, lease_id: str) -> LeaseSt:
        lease = coord.state.leases.get(lease_id)
        if lease is None or lease.reviewer != rid:
            raise HTTPException(404, "no such lease")
        return lease

    @app.get("/api/leases/{lease_id}")
    def get_lease(lease_id: str, rid: Rid) -> dict[str, Any]:
        with coord.lock:
            return lease_view(own(rid, lease_id))

    @app.post("/api/leases/{lease_id}/extend")
    def extend(lease_id: str, rid: Rid) -> dict[str, Any]:
        with coord.lock:
            return lease_view(call(coord.extend, rid, lease_id))

    @app.post("/api/leases/{lease_id}/return")
    def give_back(lease_id: str, rid: Rid) -> dict[str, bool]:
        call(coord.return_lease, rid, lease_id)
        return {"ok": True}

    @app.post("/api/leases/{lease_id}/review")
    def review(lease_id: str, req: ReviewReq, rid: Rid) -> dict[str, Any]:
        ai = AIAssistance(used=req.ai_used, provider=req.ai_provider) if req.ai_used \
            else AIAssistance()
        evidence = req.evidence.encode("utf-8") if req.evidence else None
        if evidence is not None and req.evidence_kind is None:
            raise HTTPException(400, "evidence needs a kind")
        call(coord.submit_review, rid, lease_id, verdict=req.verdict, reason=req.reason,
             failed=req.failed, evidence=evidence, evidence_kind=req.evidence_kind, ai=ai)
        return {"ok": True}

    @app.post("/api/leases/{lease_id}/claim")
    def claim(lease_id: str, req: ClaimReq, rid: Rid) -> dict[str, bool]:
        call(coord.resolve_claim, rid, lease_id, confirmed=req.confirmed, reason=req.reason)
        return {"ok": True}

    @app.get("/api/blobs/{digest}", response_class=PlainTextResponse)
    def blob(digest: str, rid: Rid) -> str:
        if coord.blobs is None:
            raise HTTPException(404, "no blob store")
        try:
            return coord.blobs.get(digest).decode("utf-8")
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, "no such file") from exc

    # ---------------------------------------------------------- maintainer
    @app.post("/api/admin/tick")
    def tick(_: Admin) -> dict[str, int]:
        return dict(coord.tick())

    @app.get("/api/admin/escalated")
    def escalated(_: Admin) -> list[dict[str, Any]]:
        with coord.lock:
            return [{"ticket_id": t.ticket_id, "declaration": t.view.declaration,
                     "paper": coord.state.submissions[t.submission_id].title,
                     "votes": [{"verdict": "incorrect" if r.incorrect else "correct",
                                "reason": r.reason} for r in t.reviews]}
                    for t in coord.state.tickets.values() if t.status == "escalate"]

    @app.post("/api/admin/tickets/{ticket_id}/decide")
    def decide(ticket_id: str, req: DecideReq, rid: Admin) -> dict[str, bool]:
        call(coord.maintainer_decide, rid, ticket_id, error=req.error, reason=req.reason)
        return {"ok": True}

    @app.post("/api/admin/submissions/{submission_id}/close")
    def close(submission_id: str, rid: Admin) -> dict[str, bool]:
        call(coord.close_submission, rid, submission_id)
        return {"ok": True}

    @app.get("/api/admin/submissions")
    def submissions(_: Admin) -> list[dict[str, Any]]:
        with coord.lock:
            out = []
            for sub in coord.state.submissions.values():
                tickets = [coord.state.tickets[t] for t in sub.tickets]
                counts: dict[str, int] = {}
                for t in tickets:
                    key = "planted_error" if t.honeypot else t.status
                    counts[key] = counts.get(key, 0) + 1
                out.append({"submission_id": sub.submission_id, "title": sub.title,
                            "repo_url": sub.repo_url, "commit": sub.commit,
                            "closed": sub.closed, "tickets": counts})
            return out

    if static_dir is not None and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app
