"""The public progress page (proposal C-26, S-23; concept §10.1, §11.1, SR-42).

Everything here is computed from the coordinator's state and is safe to show
to anyone, signed in or not:

* counts are by declaration, never by ticket (ticket counts would expose the
  number of planted errors);
* a declaration counts as decided only when all of its tickets are, so that
  nobody holding a planted copy learns that the real ticket is through;
* the Lean statement of the main theorem appears only once its discussion
  could open (decided, planted errors of the submission revealed);
* no verdict tallies of open work: only decided and confirmed results.

PRL (concept §10.1): 1 formalized and built (the submission was opened, which
needs a clean ingest), 2 the main statement confirmed faithful, 3 class A
complete. A confirmed error in class A caps the result at PRL 1 (SR-53).
PRL 4 (class B certified) and 5 (accepted by the community) come with M5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from dpc.domain.forecast import completion_weeks

if TYPE_CHECKING:
    from dpc.coord.service import Coordinator
    from dpc.coord.state import TicketSt

PRL_MEANING = {
    0: "claim only",
    1: "formalized, builds, standard axioms only",
    2: "main statement confirmed faithful",
    3: "all class-A declarations reviewed",
    4: "proof internals certified",
    5: "accepted by the community",
}


@dataclass
class Unit:
    declaration: str
    tickets: list[TicketSt]
    real: TicketSt

    @property
    def decided(self) -> bool:
        return all(t.status in ("accepted", "error") for t in self.tickets)

    @property
    def started(self) -> bool:
        return any(t.reviews for t in self.tickets)

    @property
    def decided_at(self) -> datetime | None:
        times = [t.decided_at for t in self.tickets if t.decided_at is not None]
        return max(times) if self.decided and times else None

    @property
    def state(self) -> str:
        if self.decided:
            return self.real.status  # accepted or error: the real declaration
        return "in review" if self.started else "not started"


def units(coord: Coordinator, submission_id: str) -> list[Unit]:
    st = coord.state
    by_decl: dict[str, list[TicketSt]] = {}
    for tid in st.submissions[submission_id].tickets:
        t = st.tickets[tid]
        if t.ticket_class == "A":
            by_decl.setdefault(t.view.declaration, []).append(t)
    out = []
    for decl, tickets in by_decl.items():
        real = next((t for t in tickets if not coord.vault.is_honeypot(t.ticket_id)), tickets[0])
        out.append(Unit(decl, tickets, real))
    return out


def _weekly_throughput(coord: Coordinator, weeks: int = 8) -> list[float]:
    now = coord.now()
    counts = [0.0] * weeks
    for r in coord.state.reviews.values():
        age = (now - r.ts).days // 7
        if 0 <= age < weeks:
            counts[age] += 1
    return counts


def summary(coord: Coordinator, submission_id: str) -> dict[str, Any]:
    st = coord.state
    sub = st.submissions[submission_id]
    us = units(coord, submission_id)
    decided = [u for u in us if u.decided]
    accepted = [u for u in decided if u.state == "accepted"]
    errors = [u for u in decided if u.state == "error"]
    root = next((u for u in us if u.declaration == sub.root), None)
    if errors:
        prl = 1  # a confirmed finding caps the result (SR-53)
    elif us and len(accepted) == len(us):
        prl = 3
    elif root is not None and root.state == "accepted":
        prl = 2
    else:
        prl = 1
    # P(at least one accepted declaration is wrong), from the decision rule's
    # posteriors; an estimate, as good as the calibration of trust.
    residual = 1.0 - math.prod(1.0 - (u.real.p_error or 0.0) for u in accepted) \
        if accepted else None
    remaining = sum(max(0, coord.params.parallel - u.real.review_count())
                    for u in us if not u.decided)
    forecast = None
    throughput = _weekly_throughput(coord)
    if remaining and sum(1 for w in throughput if w > 0) >= 2:
        weeks = completion_weeks(remaining, throughput, np.random.default_rng(0))
        forecast = {"p50_weeks": weeks[0.5], "p85_weeks": weeks[0.85]}
    psi = coord.attention().get(submission_id)
    paper = root.real.paper if root else None
    return {
        "submission_id": submission_id, "title": sub.title, "repo_url": sub.repo_url,
        "commit": sub.commit, "paper_ref": sub.paper_ref,
        "paper_url": paper.source.url if paper else None, "opened": sub.opened.isoformat(),
        "closed": sub.closed, "prl": prl, "prl_meaning": PRL_MEANING[prl],
        "declarations": len(us), "decided": len(decided), "accepted": len(accepted),
        "errors": len(errors), "in_review": sum(1 for u in us if u.state == "in review"),
        "not_started": sum(1 for u in us if u.state == "not started"),
        "coverage": len(decided) / len(us) if us else 0.0,
        "residual_error": residual, "forecast": forecast,
        "interest": round(psi, 3) if psi is not None else None,
        "main_statement": paper.statement if paper else None,
        "main_locator": paper.locator if paper else None,
    }


def detail(coord: Coordinator, submission_id: str, viewer: str | None) -> dict[str, Any]:
    st = coord.state
    sub = st.submissions[submission_id]
    out = summary(coord, submission_id)
    us = units(coord, submission_id)
    root = next((u for u in us if u.declaration == sub.root), None)
    show_root = root is not None and coord.thread_open(submission_id, root.declaration)
    out["main_view"] = root.real.view.model_dump(mode="json") if root and show_root else None
    out["root"] = sub.root
    out["units"] = [{
        "declaration": u.declaration, "decl_kind": u.real.view.decl_kind, "tier": u.real.tier,
        "domain": u.real.domain, "state": u.state,
        "discussion": coord.thread_open(submission_id, u.declaration),
    } for u in sorted(us, key=lambda u: (u.declaration != sub.root, u.declaration))]
    # Progress over time: decided declarations, by the day each was decided.
    points = sorted(u.decided_at for u in us if u.decided_at is not None)
    timeline = [{"at": sub.opened.isoformat(), "decided": 0}]
    for i, at in enumerate(points, start=1):
        timeline.append({"at": at.isoformat(), "decided": i})
    if not sub.closed:
        timeline.append({"at": coord.now().isoformat(), "decided": len(points)})
    out["timeline"] = timeline
    out["notes"] = notes(coord, submission_id, viewer)
    return out


def notes(coord: Coordinator, submission_id: str, viewer: str | None) -> list[dict[str, Any]]:
    """Notes of maintainers on the submission; votes of signed-in users sort them."""
    st = coord.state
    thread = (submission_id, "")
    order: list[str] = []
    out: list[dict[str, Any]] = []
    for pid in st.threads[thread]:
        p = st.posts[pid]
        if p.author not in order:
            order.append(p.author)
        named = p.author in st.named[thread]
        out.append({
            "post_id": pid, "kind": "comment",
            "author": (coord.vault.pseudonym(p.author) or "?") if named
            else f"Maintainer {chr(ord('A') + order.index(p.author))}",
            "is_me": p.author == viewer, "maintainer": True,
            "member_since": st.reviewers[p.author].registered.strftime("%Y-%m"),
            "reviewed_here": False, "at": p.at.isoformat(), "score": p.score,
            "my_vote": p.votes.get(viewer, 0) if viewer else 0, "ai_used": p.ai_used,
            "hidden": p.hidden, "text": "" if p.hidden else p.text,
        })
    out.sort(key=lambda x: (-int(x["score"]), str(x["at"])))
    return out


def overview(coord: Coordinator) -> list[dict[str, Any]]:
    subs = sorted(coord.state.submissions.values(), key=lambda s: s.opened, reverse=True)
    return [summary(coord, s.submission_id) for s in subs]
