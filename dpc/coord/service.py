"""Coordination service: the single sequencer of the review process (docs/adr/0008).

Commands are validated against the projected state, appended to the audit log
as events, and only then applied to the state (`_emit`). Random choices (choice
sets, PVV sampling) are made here and recorded as events, so replaying the log
never needs the random generator.

Process of a class-A ticket (concept §4–§9):

1. A reviewer draws a choice set (SR-38) and leases one ticket from it; the
   lease runs for ``τ = F⁻¹(1 − α)`` and can be extended once (SR-26).
2. ``k_min + 1`` persons review in parallel (SR-28). "Incorrect" needs a
   justification (SR-09) and opens a claim ticket for a PVV (SR-13, SR-35);
   "correct" is re-checked by a PVV with probability ``ρ_u``.
3. The decision rule (SR-11) runs when enough votes are in and nothing is
   pending; acceptance needs a PVV review. Open claims block (one-finding rule).
4. Honeypots are revealed with delay and in batches (SR-37); then the soft
   evidence on them is replaced by the hard one.
"""

from __future__ import annotations

import re
import secrets
import threading
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from pydantic import BaseModel, ValidationError

from dpc.audit.log import AuditLog, Entry, utc_now
from dpc.coord import events as ev
from dpc.coord.params import DAY, CoordParams
from dpc.coord.state import (
    ChoiceSetSt,
    ClaimSt,
    LeaseSt,
    ReviewerSt,
    State,
    TicketSt,
    difficulty_bucket,
)
from dpc.coord.tiers import TIERS, Tier, tier_of, tier_open
from dpc.coord.vault import BlobStore, Vault
from dpc.domain.attention import Choice, fit_plackett_luce
from dpc.domain.decision import Vote, decide, posterior_error
from dpc.domain.lease import lease_duration
from dpc.domain.review import recheck_probability
from dpc.domain.trust import time_factor
from dpc.honeypots.mixing import plan_stream
from dpc.honeypots.sources import HoneypotPool
from dpc.tickets.model import AIAssistance, Evidence, Review
from dpc.tickets.views import UnitView

#: Version of the registration notice on the use of review data (SR-49).
NOTICE_VERSION = "2026-11-registration-v1"

_PSEUDONYM = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class CoordError(Exception):
    status = 400


class NotFound(CoordError):
    status = 404


class Forbidden(CoordError):
    status = 403


class Conflict(CoordError):
    status = 409


@dataclass(frozen=True)
class TicketSpec:
    view: UnitView
    domain: str
    difficulty: float = 0.0


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


class Coordinator:
    def __init__(
        self,
        log: AuditLog,
        vault: Vault,
        params: CoordParams | None = None,
        *,
        blobs: BlobStore | None = None,
        clock: Callable[[], datetime] = utc_now,
        rng: np.random.Generator | None = None,
        new_id: Callable[[str], str] = _id,
    ) -> None:
        self.log, self.vault, self.blobs = log, vault, blobs
        self.params = params or CoordParams()
        self.clock, self.new_id = clock, new_id
        self.rng = rng or np.random.default_rng()
        self.lock = threading.RLock()
        self.state = State(self.params)
        for entry in log.entries():
            self.state.apply(entry)
        config = self.params.as_log()
        if not self.state.configured or self.state.configured[-1] != config:
            self._emit("coord.configured", ev.CoordConfigured(params=config))

    # ------------------------------------------------------------ helpers
    def _emit(self, kind: str, payload: BaseModel) -> Entry:
        entry = self.log.append(kind, payload.model_dump(mode="json"))
        self.state.apply(entry)
        return entry

    def now(self) -> datetime:
        return self.clock()

    def _reviewer(self, rid: str) -> None:
        if rid not in self.state.reviewers:
            raise NotFound(f"unknown reviewer {rid}")

    def _ticket(self, ticket_id: str) -> TicketSt:
        ticket = self.state.tickets.get(ticket_id)
        if ticket is None:
            raise NotFound(f"unknown ticket {ticket_id}")
        return ticket

    def _own_lease(self, rid: str, lease_id: str) -> LeaseSt:
        lease = self.state.leases.get(lease_id)
        if lease is None or lease.reviewer != rid:
            raise NotFound(f"no lease {lease_id}")
        if lease.status != "active":
            raise Conflict(f"lease {lease_id} is {lease.status}")
        if self.now() >= lease.expires:
            self._emit("lease.expired", ev.LeaseEnded(lease_id=lease_id))
            raise Conflict(f"lease {lease_id} has expired")
        return lease

    def _maintainer(self, rid: str) -> None:
        self._reviewer(rid)
        if not self.state.reviewers[rid].maintainer:
            raise Forbidden("maintainers only")

    # ------------------------------------------------------- registration
    def register(self, pseudonym: str, group: ev.Group = "other", affiliations: Sequence[str] = (),
                 *, notice_acknowledged: bool,
                 identity: tuple[str, str] | None = None) -> tuple[str, str]:
        """Pseudonymous account (SR-23). Returns ``(reviewer id, API token)``.

        ``identity``: ``(provider, subject)`` of an external sign-in, linked to
        the new reviewer in the vault. The log never sees it."""
        if not _PSEUDONYM.match(pseudonym):
            raise CoordError("pseudonym: 3–32 characters out of letters, digits, '_', '.', '-'")
        if not notice_acknowledged:
            raise Forbidden(f"registration requires acknowledging notice {NOTICE_VERSION} "
                            "(review data is openly licensed and may be used for training, SR-49)")
        with self.lock:
            if identity is not None and self.vault.reviewer_for_identity(*identity):
                raise Conflict("this sign-in already has a reviewer account")
            try:
                rid, token = self.vault.create_account(pseudonym)
            except ValueError as exc:
                raise Conflict(str(exc)) from exc
            if identity is not None:
                self.vault.link_identity(*identity, rid)
            tags = tuple(sorted({self.vault.tag(a) for a in affiliations if a.strip()}))
            self._emit("reviewer.registered", ev.ReviewerRegistered(
                reviewer=rid, group=group, affiliation_tags=tags, notice=NOTICE_VERSION))
            return rid, token

    def declare_affiliation(self, rid: str, lab: str) -> None:
        """Employment by or commission from a lab (SR-50); can only be added."""
        with self.lock:
            self._reviewer(rid)
            self._emit("reviewer.affiliation_declared",
                       ev.AffiliationDeclared(reviewer=rid, tag=self.vault.tag(lab)))

    def appoint_maintainer(self, rid: str) -> None:
        with self.lock:
            self._reviewer(rid)
            self._emit("reviewer.maintainer_appointed", ev.MaintainerAppointed(reviewer=rid))

    def set_preferences(self, rid: str, *, domains: Sequence[str] = (),
                        tiers: Sequence[str] = ()) -> None:
        """What the reviewer wants to work on (SR-32: raises the chance only)."""
        domains = tuple(sorted({d.strip() for d in domains if d.strip()}))
        if len(domains) > 20 or any(len(d) > 64 for d in domains):
            raise CoordError("at most 20 domains of at most 64 characters")
        unknown = [t for t in tiers if t not in TIERS]
        if unknown:
            raise CoordError(f"unknown tiers {unknown}; known: {list(TIERS)}")
        with self.lock:
            self._reviewer(rid)
            self._emit("reviewer.preferences_set", ev.PreferencesSet(
                reviewer=rid, domains=domains,
                tiers=tuple(t for t in TIERS if t in tiers)))

    def tiers_open(self, rid: str, domain: str | None = None) -> list[Tier]:
        """Tiers the reviewer may take (in ``domain``, or in any domain)."""
        st, now = self.state, self.now()
        person = st.reviewers[rid]
        domains = [domain] if domain is not None else sorted(
            {e.domain for e in person.evidence}) or [""]
        return [t for t in TIERS if any(
            tier_open(t, roles=st.roles(rid, d, now), group=person.group,
                      maintainer=person.maintainer) for d in domains)]

    def sync_maintainer(self, rid: str, granted: bool) -> None:
        """Follow the maintainer role of an identity provider (docs/adr/0010).
        Every change is logged. Appointments by the operator are left alone."""
        with self.lock:
            self._reviewer(rid)
            person = self.state.reviewers[rid]
            if granted and not person.maintainer:
                self._emit("reviewer.maintainer_appointed",
                           ev.MaintainerAppointed(reviewer=rid, by="identity_provider"))
            elif not granted and person.maintainer_by == "identity_provider":
                self._emit("reviewer.maintainer_revoked",
                           ev.MaintainerRevoked(reviewer=rid, by="identity_provider"))

    # --------------------------------------------------------- submissions
    def open_submission(
        self, *, title: str, repo_url: str, commit: str, tickets: Sequence[TicketSpec],
        pool: HoneypotPool | None = None, share: float | None = None, lab: str | None = None,
        authors: Sequence[str] = (), artifact_key: str | None = None,
    ) -> str:
        """Create the class-A tickets (SR-05) with honeypots mixed in (SR-06)."""
        share = self.params.honeypot_share if share is None else share
        with self.lock:
            sid = self.new_id("S")
            specs = {t.view.declaration: t for t in tickets}
            if len(specs) != len(tickets):
                raise CoordError("one ticket per unit")
            slots = plan_stream([t.view for t in tickets],
                                pool or HoneypotPool([], self.rng), self.rng, share=share)
            self._emit("submission.opened", ev.SubmissionOpened(
                submission_id=sid, title=title, repo_url=repo_url, commit=commit,
                artifact_key=artifact_key, lab_tag=self.vault.tag(lab) if lab else None,
                authors=tuple(authors)))
            for slot in slots:
                spec = specs[slot.view.declaration]
                tid = self.new_id("A")
                cand = slot.honeypot
                opening = ev.Opening(
                    ticket_id=tid, honeypot=slot.is_honeypot, salt=secrets.token_hex(16),
                    mutant_hash=cand.mutant.mutant_hash if cand else None,
                    operator=cand.mutant.operator if cand else None,
                    source=cand.source if cand else None)
                self._emit("ticket.created", ev.TicketCreated(
                    ticket_id=tid, submission_id=sid, ticket_class="A", view=slot.view,
                    domain=spec.domain, difficulty=ev.dec(spec.difficulty),
                    slots=self.params.parallel,
                    commitment=self.vault.put_opening(sid, opening)))
            return sid

    def close_submission(self, rid: str, submission_id: str) -> None:
        """Close a submission and open every remaining commitment."""
        with self.lock:
            self._maintainer(rid)
            sub = self.state.submissions.get(submission_id)
            if sub is None or sub.closed:
                raise Conflict("no open submission with this id")
            for lease in self.state.active_leases():
                if self.state.tickets[lease.ticket_id].submission_id == submission_id:
                    self._emit("lease.cancelled", ev.LeaseEnded(lease_id=lease.lease_id))
            self._emit("submission.closed", ev.SubmissionClosed(submission_id=submission_id))
            openings = self.vault.unrevealed(honeypots_only=False, submission_id=submission_id)
            self._reveal(openings, final=True, submission_id=submission_id)

    # -------------------------------------------------------- eligibility
    def why_not(self, rid: str, ticket: TicketSt, duty: str) -> str | None:
        """Reason why ``rid`` may not take ``duty`` on ``ticket`` (None: allowed)."""
        st, now = self.state, self.now()
        person = st.reviewers[rid]
        sub = st.submissions[ticket.submission_id]
        if not st.is_open(ticket):
            return "ticket is not open"
        if rid in sub.authors:
            return "authors do not review their own submission (SR-08)"
        if sub.lab_tag and sub.lab_tag in person.affiliation_tags:
            return "affiliated with the submitting lab (SR-50)"
        people = st.participants(ticket)
        if rid in people:
            return "already involved in this ticket (SR-08)"
        if (sub.submission_id, ticket.view.declaration) in st.seen_units[rid]:
            # Never two tickets of the same unit: a honeypot would stand out (SR-06).
            return "already worked on this declaration"
        if duty == "review" and self.params.tier_gating and \
                now - ticket.created < timedelta(seconds=self.params.tier_gate_age_s):
            tier = tier_of(ticket.difficulty)
            if not tier_open(tier, roles=st.roles(rid, ticket.domain, now), group=person.group,
                             maintainer=person.maintainer):
                return f"{tier} tickets need more experience in this domain"
        window = timedelta(seconds=self.params.pair_window_s)
        for p in people:
            last = st.pairs.get(frozenset((rid, p)))
            if last is not None and now - last < window:
                return "pair repetition within Δ_pair (SR-08)"
        if len(st.active_leases(rid)) >= person.reliability.wip_limit(ticket.ticket_class):
            return "work-in-progress limit reached (SR-27)"
        if duty == "review":
            holding = sum(1 for lease in st.active_leases(ticket_id=ticket.ticket_id)
                          if lease.duty == "review")
            if ticket.review_count() + holding >= ticket.slots:
                return "no free review slot"
        elif duty == "pvv":
            if not ticket.needs_pvv():
                return "no PVV review requested"
            if any(lease.duty == "pvv" for lease in st.active_leases(ticket_id=ticket.ticket_id)):
                return "PVV review already leased"
            if "PVV" not in st.roles(rid, ticket.domain, now):
                return "PVV role required (SR-13)"
        return None

    def why_not_claim(self, rid: str, claim: ClaimSt) -> str | None:
        st = self.state
        ticket = st.tickets[claim.ticket_id]
        if claim.status != "open":
            return "claim is resolved"
        if not st.is_open(ticket):
            return "ticket is closed"
        if rid == claim.claimant:
            return "no self-review (SR-08)"
        if any(lease.claim_id == claim.claim_id for lease in st.active_leases()):
            return "claim already leased"
        if "PVV" not in st.roles(rid, ticket.domain, self.now()):
            return "PVV role required (SR-35)"
        sub = st.submissions[ticket.submission_id]
        person = st.reviewers[rid]
        if rid in sub.authors or (sub.lab_tag and sub.lab_tag in person.affiliation_tags):
            return "excluded from this submission (SR-08, SR-50)"
        if rid in st.participants(ticket):
            return "already involved in this ticket (SR-08)"
        last = st.pairs.get(frozenset((rid, claim.claimant)))
        if last is not None and self.now() - last < timedelta(seconds=self.params.pair_window_s):
            return "pair repetition within Δ_pair (SR-08)"
        if len(st.active_leases(rid)) >= person.reliability.wip_limit("A"):
            return "work-in-progress limit reached (SR-27)"
        return None

    # --------------------------------------------------------- choice sets
    def choice_set(self, rid: str) -> ChoiceSetSt | None:
        """The reviewer's current choice set, or a new one (SR-38, SR-39).

        Tickets come from different papers where possible, in random order, at
        most one per declaration; no popularity is shown. ``None``: nothing to
        do for this reviewer right now."""
        with self.lock:
            self._reviewer(rid)
            st, now = self.state, self.now()
            person = st.reviewers[rid]
            current = st.choice_sets.get(st.latest_set.get(rid, ""))
            if current and not current.consumed and now < current.expires and any(
                    self.why_not(rid, st.tickets[t], "review") is None for t in current.tickets):
                return current
            recent = [t for t in st.sets_drawn[rid] if now - t < timedelta(days=1)]
            if len(recent) >= self.params.max_choice_sets_per_day:
                raise Conflict("too many choice sets today")
            eligible = [t for t in st.tickets.values()
                        if t.ticket_class == "A" and self.why_not(rid, t, "review") is None]
            if not eligible:
                return None
            order = [eligible[i] for i in self.rng.permutation(len(eligible))]
            # Preferred tickets first (SR-32: preferences raise the chance only);
            # the rest fills the set, so nobody is left without tickets.
            preferred = [t for t in order if _preferred(person, t)]
            others = [t for t in order if not _preferred(person, t)]
            picked: list[TicketSt] = []
            units: set[tuple[str, str]] = set()
            for pool in (preferred, others):
                for distinct_papers in (True, False):
                    papers = {t.submission_id for t in picked}
                    for t in pool:
                        unit = (t.submission_id, t.view.declaration)
                        if len(picked) >= self.params.choice_set_size or unit in units:
                            continue
                        if distinct_papers and t.submission_id in papers:
                            continue
                        picked.append(t)
                        units.add(unit)
                        papers.add(t.submission_id)
            set_id = self.new_id("CS")
            expires = now + timedelta(seconds=self.params.choice_set_ttl_s)
            self._emit("choice_set.drawn", ev.ChoiceSetDrawn(
                set_id=set_id, reviewer=rid, tickets=tuple(t.ticket_id for t in picked),
                expires_at=ev.ts(expires)))
            return st.choice_sets[set_id]

    # -------------------------------------------------------------- leases
    def lease_duration(self, duty: str, ticket: TicketSt) -> tuple[int, int]:
        """``(τ, expected)`` in seconds; τ from finished tickets of the same duty
        and difficulty (SR-26), the expected duration is their median (SR-30)."""
        done = self.state.durations.get((duty, difficulty_bucket(ticket.difficulty)), [])
        if len(done) < self.params.lease_min_samples:
            return self.params.default_lease_s, self.params.default_expected_s
        tau = max(3600, int(lease_duration(done, self.params.lease_alpha)))
        return tau, int(np.median(done))

    def _grant(self, rid: str, duty: ev.Duty, ticket: TicketSt, *, set_id: str | None = None,
               claim_id: str | None = None) -> LeaseSt:
        tau, expected = self.lease_duration(duty, ticket)
        lease_id = self.new_id("L")
        self._emit("lease.granted", ev.LeaseGranted(
            lease_id=lease_id, reviewer=rid, duty=duty, ticket_id=ticket.ticket_id,
            claim_id=claim_id, set_id=set_id,
            expires_at=ev.ts(self.now() + timedelta(seconds=tau)), expected_s=expected))
        return self.state.leases[lease_id]

    def lease(self, rid: str, set_id: str, ticket_id: str) -> LeaseSt:
        """Take a ticket from the choice set: the choice is binding (SR-38)."""
        with self.lock:
            self._reviewer(rid)
            cs = self.state.choice_sets.get(set_id)
            if cs is None or cs.reviewer != rid:
                raise NotFound("no such choice set")
            if cs.consumed or self.now() >= cs.expires:
                raise Conflict("choice set is used up or expired")
            if ticket_id not in cs.tickets:
                raise CoordError("ticket is not in the choice set")
            ticket = self._ticket(ticket_id)
            reason = self.why_not(rid, ticket, "review")
            if reason:
                raise Conflict(reason)
            return self._grant(rid, "review", ticket, set_id=set_id)

    def next_duty(self, rid: str) -> LeaseSt | None:
        """PVV work: claims first (they block acceptance), then PVV reviews."""
        with self.lock:
            self._reviewer(rid)
            st = self.state
            for claim in sorted(st.claims.values(), key=lambda c: c.opened):
                if self.why_not_claim(rid, claim) is None:
                    return self._grant(rid, "claim", st.tickets[claim.ticket_id],
                                       claim_id=claim.claim_id)
            for ticket in sorted(st.tickets.values(), key=lambda t: t.created):
                if ticket.needs_pvv() and self.why_not(rid, ticket, "pvv") is None:
                    return self._grant(rid, "pvv", ticket)
            return None

    def extend(self, rid: str, lease_id: str) -> LeaseSt:
        """Once, by another τ (SR-26)."""
        with self.lock:
            lease = self._own_lease(rid, lease_id)
            if lease.extended:
                raise Conflict("a lease can be extended once")
            tau, _ = self.lease_duration(lease.duty, self.state.tickets[lease.ticket_id])
            self._emit("lease.extended", ev.LeaseExtended(
                lease_id=lease_id, expires_at=ev.ts(lease.expires + timedelta(seconds=tau))))
            return lease

    def return_lease(self, rid: str, lease_id: str) -> None:
        """Giving a ticket back actively carries no penalty (SR-26)."""
        with self.lock:
            lease = self._own_lease(rid, lease_id)
            self._emit("lease.returned", ev.LeaseEnded(lease_id=lease_id))
            self._evaluate(lease.ticket_id)

    # ------------------------------------------------------------- reviews
    def submit_review(
        self, rid: str, lease_id: str, *, verdict: str, reason: str = "",
        failed: Sequence[str] = (), evidence: bytes | None = None,
        evidence_kind: str | None = None, ai: AIAssistance | None = None,
    ) -> Entry:
        with self.lock:
            lease = self._own_lease(rid, lease_id)
            if lease.duty not in ("review", "pvv"):
                raise CoordError("this lease is a claim; resolve it instead")
            ticket = self.state.tickets[lease.ticket_id]
            now = self.now()
            spent = int((now - lease.granted).total_seconds())
            stored = self._store_evidence(evidence, evidence_kind)
            try:  # SR-09: the review record validates verdict and justification
                review = Review(ticket_id=ticket.ticket_id, reviewer=rid,
                                verdict=verdict, reason=reason,
                                failed=tuple(dict.fromkeys(failed)),
                                evidence=stored, time_spent_s=spent, ai=ai or AIAssistance())
            except ValidationError as exc:
                raise CoordError(exc.errors()[0]["msg"]) from exc
            if review.verdict == "incorrect" and \
                    len(review.reason.strip()) < self.params.min_reason_chars:
                raise CoordError(f"the justification needs at least "
                                 f"{self.params.min_reason_chars} characters (SR-09)")
            factor = time_factor(spent, self.params.t_min(ticket.difficulty))
            roles = tuple(sorted(self.state.roles(rid, ticket.domain, now)))
            entry = self._emit("review.submitted", ev.ReviewSubmitted(
                lease_id=lease_id, ticket_id=ticket.ticket_id, reviewer=rid,
                duty=lease.duty,
                round=ticket.round, verdict=review.verdict, reason=review.reason,
                failed=review.failed, evidence=review.evidence, ai=review.ai,
                time_spent_s=spent,
                t_factor=ev.dec(factor), roles=roles))
            if review.verdict == "incorrect" and ticket.ticket_class == "A":
                # SR-35: a justified finding becomes a claim ticket for a PVV (SR-13).
                self._emit("claim.opened", ev.ClaimOpened(
                    claim_id=self.new_id("C"), ticket_id=ticket.ticket_id, claimant=rid,
                    review_seq=entry.seq))
            elif lease.duty == "review":
                kappa = self.state.trust(rid, ticket.domain, now).kappa()
                rho = recheck_probability(kappa, incorrect=False, ticket_class="A",
                                          rho_min=self.params.rho_min,
                                          rho_max=self.params.rho_max)
                if self.rng.random() < rho:
                    self._emit("pvv.requested", ev.PvvRequested(
                        ticket_id=ticket.ticket_id, review_seq=entry.seq, reason="sample"))
            self._evaluate(ticket.ticket_id)
            return entry

    def _store_evidence(self, data: bytes | None, kind: str | None) -> Evidence | None:
        if data is None:
            return None
        if len(data) > self.params.max_evidence_bytes:
            raise CoordError("evidence file too large")
        if self.blobs is None:
            raise CoordError("evidence files are not accepted by this server")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CoordError("evidence must be a UTF-8 Lean file") from exc
        digest = self.blobs.put(data)
        try:
            return Evidence(kind=kind, file_sha256=digest)
        except ValidationError as exc:
            raise CoordError(exc.errors()[0]["msg"]) from exc

    def resolve_claim(self, rid: str, lease_id: str, *, confirmed: bool, reason: str) -> None:
        """A PVV decides a claim ticket (SR-35): the concrete finding, not a vote."""
        if not reason.strip():
            raise CoordError("a claim decision needs a justification")
        with self.lock:
            lease = self._own_lease(rid, lease_id)
            if lease.duty != "claim" or lease.claim_id is None:
                raise CoordError("this lease is not a claim")
            by = "maintainer" if self.state.reviewers[rid].maintainer else "pvv"
            self._emit("claim.resolved", ev.ClaimResolved(
                claim_id=lease.claim_id, confirmed=confirmed, by=by,
                resolver=rid, lease_id=lease_id, reason=reason))
            self._evaluate(lease.ticket_id)

    def confirm_by_machine(self, claim_id: str, detail: str) -> None:
        """Machine-checked evidence (SR-10) confirms a claim: a hard anchor."""
        with self.lock:
            claim = self.state.claims.get(claim_id)
            if claim is None or claim.status != "open":
                raise Conflict("no open claim with this id")
            for lease in self.state.active_leases():
                if lease.claim_id == claim_id:
                    self._emit("lease.cancelled", ev.LeaseEnded(lease_id=lease.lease_id))
            self._emit("claim.resolved", ev.ClaimResolved(
                claim_id=claim_id, confirmed=True, by="machine", reason=detail))
            self._evaluate(claim.ticket_id)

    def maintainer_decide(self, rid: str, ticket_id: str, *, error: bool, reason: str) -> None:
        """Escalated tickets (concept §6.4: after R rounds) go to maintainers."""
        with self.lock:
            self._maintainer(rid)
            ticket = self._ticket(ticket_id)
            if ticket.status != "escalate":
                raise Conflict("only escalated tickets are decided by maintainers")
            self._emit("ticket.decided", ev.TicketDecided(
                ticket_id=ticket_id, outcome="error" if error else "accepted",
                p_error=ev.dec(1.0 if error else 0.0),
                independent_votes=len(ticket.reviews), by="maintainer", maintainer=rid,
                reason=reason))

    # ------------------------------------------------------------ decision
    def _evaluate(self, ticket_id: str) -> None:
        st, params = self.state, self.params
        ticket = st.tickets[ticket_id]
        if not st.is_open(ticket):
            return
        if ticket.error_confirmed:  # a confirmed finding decides; pending work is moot
            for lease in st.active_leases(ticket_id=ticket_id):
                self._emit("lease.cancelled", ev.LeaseEnded(lease_id=lease.lease_id))
            self._emit("ticket.decided", ev.TicketDecided(
                ticket_id=ticket_id, outcome="error", p_error=ev.dec(1.0),
                independent_votes=len(ticket.reviews)))
            return
        if any(st.claims[c].status == "open" for c in ticket.claims):
            return  # one-finding rule: an open claim blocks (SR-35)
        if st.active_leases(ticket_id=ticket_id) or ticket.needs_pvv():
            return  # wait for everyone holding the ticket and for requested PVV reviews
        n_reviews = ticket.review_count()
        free = ticket.slots - n_reviews
        if n_reviews < params.decision.k_min and free > 0:
            return
        now = self.now()
        votes = []
        for r in ticket.reviews:
            s_hat, c_hat = st.trust(r.reviewer, ticket.domain, now).point_estimates()
            votes.append(Vote(r.reviewer, r.incorrect, s_hat, c_hat))
        refuted = ticket.error_confirmed
        pvv_reviewed = any(r.duty == "pvv" or "PVV" in r.roles for r in ticket.reviews)
        p = posterior_error(votes, params.decision.prior_error)
        if (not refuted and not pvv_reviewed and p < params.decision.delta_a
                and len(votes) >= params.decision.k_min):
            self._emit("pvv.requested", ev.PvvRequested(ticket_id=ticket_id, reason="decision"))
            return
        decision = decide(votes, params.decision, pvv_reviewed=pvv_reviewed, refuted=refuted,
                          rounds=ticket.round)
        outcome = decision.outcome.value
        if outcome in ("accepted", "error", "escalate"):
            self._emit("ticket.decided", ev.TicketDecided(
                ticket_id=ticket_id, outcome=outcome,
                p_error=ev.dec(decision.p_error), independent_votes=decision.independent_votes))
        elif free <= 0:
            self._emit("ticket.round_opened", ev.RoundOpened(
                ticket_id=ticket_id, round=ticket.round + 1,
                slots=ticket.slots + params.slots_per_extra_round))

    # ---------------------------------------------------------------- tick
    def tick(self) -> dict[str, int]:
        """Periodic work: expire leases, reveal due honeypots (SR-27, SR-37)."""
        with self.lock:
            now = self.now()
            expired = [lease for lease in self.state.active_leases() if lease.expires <= now]
            for lease in expired:
                self._emit("lease.expired", ev.LeaseEnded(lease_id=lease.lease_id))
                self._evaluate(lease.ticket_id)
            delay = timedelta(seconds=self.params.reveal_delay_s)
            due = [o for o in self.vault.unrevealed(honeypots_only=True)
                   if (t := self.state.tickets[o.ticket_id]).decided_at is not None
                   and now - t.decided_at >= delay]
            revealed = 0
            if len(due) >= self.params.reveal_batch:
                self._reveal(due, final=False, submission_id=None)
                revealed = len(due)
            return {"expired": len(expired), "revealed": revealed}

    def _reveal(self, openings: list[ev.Opening], *, final: bool,
                submission_id: str | None) -> None:
        if not openings:
            return
        self._emit("honeypots.revealed", ev.HoneypotsRevealed(
            submission_id=submission_id, final=final, openings=tuple(openings)))
        self.vault.mark_revealed([o.ticket_id for o in openings])

    # ------------------------------------------------------------- queries
    def attention(self, group: str | None = None) -> dict[str, float]:
        """Interest ψ per paper from binding choices (SR-38). Only choices
        followed by finished work count, weighted by the chooser's trust."""
        st, now = self.state, self.now()
        choices = []
        for lease in st.leases.values():
            if lease.set_id is None or lease.status != "done":
                continue
            if group is not None and st.reviewers[lease.reviewer].group != group:
                continue
            shown = tuple(sorted({st.tickets[t].submission_id
                                  for t in st.choice_sets[lease.set_id].tickets}))
            ticket = st.tickets[lease.ticket_id]
            weight = max(0.05, st.trust(lease.reviewer, ticket.domain, now).kappa())
            choices.append(Choice(shown, ticket.submission_id, weight))
        return fit_plackett_luce(choices)

    def stats(self) -> dict[str, object]:
        """Aggregates only (SR-23)."""
        st, now = self.state, self.now()
        by_status = Counter("honeypot" if t.honeypot else t.status for t in st.tickets.values())
        week = [r for r in st.reviews.values() if now - r.ts < timedelta(seconds=7 * DAY)]
        return {
            "reviewers": len(st.reviewers),
            "reviewers_by_group": dict(sorted(Counter(
                r.group for r in st.reviewers.values()).items())),
            "submissions": len(st.submissions),
            "tickets_by_status": dict(sorted(by_status.items())),
            "reviews_last_7_days": len(week),
            "open_claims": sum(1 for c in st.claims.values() if c.status == "open"),
            "active_leases": len(st.active_leases()),
            "audit_head": head.hash if (head := self.log.head()) else None,
        }


def _preferred(person: ReviewerSt, ticket: TicketSt) -> bool:
    """Does the ticket match the reviewer's preferences (none set: all do)?"""
    return ((not person.pref_domains or ticket.domain in person.pref_domains)
            and (not person.pref_tiers or tier_of(ticket.difficulty) in person.pref_tiers))
