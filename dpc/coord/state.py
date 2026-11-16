"""Projection of the audit log onto the coordination state (docs/adr/0008).

:meth:`State.apply` is the only way the state changes; replaying the log from
the start reproduces it exactly. Trust is not stored but folded on demand from
the evidence records, so that a honeypot reveal can *replace* the soft evidence
collected on that ticket (PVV comparison, consensus) by the hard one.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from dpc.audit.log import Entry
from dpc.coord import events as ev
from dpc.coord.params import DAY, CoordParams
from dpc.coord.tiers import Tier, tier_of
from dpc.domain.anomaly import DetectionRecord
from dpc.domain.lease import Reliability
from dpc.domain.trust import Source, TrustState, record
from dpc.tickets.model import Evidence
from dpc.tickets.paper import PaperPassage
from dpc.tickets.views import UnitView

LeaseStatus = Literal["active", "done", "returned", "expired", "cancelled"]
TicketStatus = Literal["open", "accepted", "error", "escalate"]


@dataclass(frozen=True)
class EvidenceRec:
    ts: datetime
    domain: str
    said_incorrect: bool
    source: Source
    p_error: float
    factor: float  # time factor of the underlying review (SR-29)
    ticket_id: str


@dataclass
class ReviewerSt:
    rid: str
    group: str
    registered: datetime
    affiliation_tags: set[str] = field(default_factory=set)
    maintainer: bool = False
    maintainer_by: str | None = None  # "operator" or "identity_provider"
    pref_domains: tuple[str, ...] = ()
    pref_tiers: tuple[str, ...] = ()
    prefs_at: datetime | None = None
    reliability: Reliability = field(default_factory=Reliability)
    evidence: list[EvidenceRec] = field(default_factory=list)
    detections: DetectionRecord = field(default_factory=DetectionRecord)


@dataclass(frozen=True)
class ReviewRec:
    seq: int
    ts: datetime
    lease_id: str
    ticket_id: str
    reviewer: str
    duty: str
    round: int
    incorrect: bool
    reason: str
    time_spent_s: int
    t_factor: float
    roles: tuple[str, ...]
    evidence: Evidence | None = None
    failed: tuple[str, ...] = ()


@dataclass
class LeaseSt:
    lease_id: str
    reviewer: str
    duty: str
    ticket_id: str
    claim_id: str | None
    set_id: str | None
    granted: datetime
    expires: datetime
    expected_s: int
    extended: bool = False
    status: LeaseStatus = "active"


@dataclass
class ClaimSt:
    claim_id: str
    ticket_id: str
    claimant: str
    review_seq: int
    opened: datetime
    status: Literal["open", "confirmed", "rejected"] = "open"
    by: str | None = None
    resolver: str | None = None


@dataclass
class TicketSt:
    ticket_id: str
    submission_id: str
    ticket_class: str
    view: UnitView
    domain: str
    difficulty: float
    commitment: str
    created: datetime
    slots: int
    round: int = 1
    reviews: list[ReviewRec] = field(default_factory=list)
    pvv_pending: list[int] = field(default_factory=list)  # review seqs to compare with
    pvv_for_decision: bool = False
    claims: list[str] = field(default_factory=list)
    status: TicketStatus = "open"
    p_error: float | None = None
    decided_at: datetime | None = None
    error_confirmed: bool = False
    honeypot: bool | None = None  # None until the commitment is opened
    paper: PaperPassage | None = None
    tier: Tier = "medium"
    #: (reviewer, reason) of every contest of the paper mapping (SR-24)
    contests: list[tuple[str, str]] = field(default_factory=list)

    def review_count(self) -> int:
        return sum(1 for r in self.reviews if r.duty == "review")

    def needs_pvv(self) -> bool:
        return bool(self.pvv_pending) or self.pvv_for_decision


@dataclass
class SubmissionSt:
    submission_id: str
    title: str
    repo_url: str
    commit: str
    lab_tag: str | None
    authors: tuple[str, ...]
    opened: datetime
    closed: bool = False
    tickets: list[str] = field(default_factory=list)
    paper_ref: str | None = None
    root: str | None = None
    basis: ev.BasisRecorded | None = None  # what the result relies on (C-29)
    tags: tuple[str, ...] = ()  # hashtags of the problem, set by maintainers (C-44)


@dataclass
class ChoiceSetSt:
    set_id: str
    reviewer: str
    tickets: tuple[str, ...]
    drawn: datetime
    expires: datetime
    consumed: bool = False
    preferences_applied: bool = False
    at_limit: bool = False
    used: bool = False  # a ticket was taken from it and not given up (C-32)


def _days(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / DAY)


@dataclass
class PostSt:
    post_id: str
    thread: tuple[str, str]  # (submission id, declaration)
    author: str
    kind: str  # "review" or "comment"
    text: str
    review_seq: int | None
    at: datetime
    ai_used: bool = False
    votes: dict[str, int] = field(default_factory=dict)
    reports: list[tuple[str, str]] = field(default_factory=list)
    hidden: str | None = None  # reason, if a maintainer hid it

    @property
    def score(self) -> int:
        return sum(self.votes.values())


@dataclass
class ReopenSt:
    request_id: str
    ticket_id: str
    post_id: str | None
    requester: str
    reason: str
    at: datetime
    status: str = "open"  # open, reopened, dismissed


class State:
    def __init__(self, params: CoordParams) -> None:
        self.params = params
        self.reviewers: dict[str, ReviewerSt] = {}
        self.submissions: dict[str, SubmissionSt] = {}
        self.tickets: dict[str, TicketSt] = {}
        self.leases: dict[str, LeaseSt] = {}
        self.active: dict[str, LeaseSt] = {}  # index: active leases only
        self.seen_units: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self.claims: dict[str, ClaimSt] = {}
        self.choice_sets: dict[str, ChoiceSetSt] = {}
        self.latest_set: dict[str, str] = {}
        self.sets_drawn: dict[str, list[datetime]] = defaultdict(list)
        self.sets_of: dict[str, list[str]] = defaultdict(list)  # set ids per reviewer
        # when each reviewer changed preferences (C-32: a change is a reroll)
        self.pref_changes: dict[str, list[datetime]] = defaultdict(list)
        self.reviews: dict[int, ReviewRec] = {}
        self.pairs: dict[frozenset[str], datetime] = {}
        self.durations: dict[tuple[str, int], list[int]] = defaultdict(list)
        self.configured: list[dict[str, object]] = []
        # discussion after the decision (C-25)
        self.posts: dict[str, PostSt] = {}
        self.threads: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.named: dict[tuple[str, str], set[str]] = defaultdict(set)  # pseudonym shown
        # votes on a thread: whether it is worth reading (sorting only)
        self.thread_votes: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
        self.reopens: dict[str, ReopenSt] = {}
        self.seq = -1
        # Roles per (reviewer, domain, time), valid until the next event: a
        # choice set asks for them once per ticket (SR-22).
        self._roles: dict[tuple[str, str, datetime], frozenset[str]] = {}
        self._roles_seq = -1

    # ------------------------------------------------------------- queries
    def trust(self, rid: str, domain: str, at: datetime) -> TrustState:
        """Fold the evidence of one person in one domain, with decay λ (SR-12)."""
        weights = self.params.source_weights()
        lam = self.params.decay_per_day
        state, last = TrustState(), None
        for e in self.reviewers[rid].evidence:
            if e.domain != domain:
                continue
            if last is not None:
                state = state.decay(lam, _days(last, e.ts))
            state = record(state, e.said_incorrect, e.source, p_error=e.p_error,
                           time_factor=e.factor, weights=weights)
            last = e.ts
        if last is not None:
            state = state.decay(lam, _days(last, at))
        return state

    def roles(self, rid: str, domain: str, at: datetime) -> frozenset[str]:
        if self._roles_seq != self.seq:
            self._roles.clear()
            self._roles_seq = self.seq
        key = (rid, domain, at)
        cached = self._roles.get(key)
        if cached is not None:
            return cached
        reviewer = self.reviewers[rid]
        roles = set(self.params.roles.roles(self.trust(rid, domain, at)))
        if reviewer.maintainer:
            roles |= {"PV", "PVV", "maintainer"}
        self._roles[key] = frozenset(roles)
        return self._roles[key]

    def active_leases(self, rid: str | None = None, ticket_id: str | None = None
                      ) -> list[LeaseSt]:
        return [lease for lease in self.active.values()
                if (rid is None or lease.reviewer == rid)
                and (ticket_id is None or lease.ticket_id == ticket_id)]

    def participants(self, ticket: TicketSt) -> set[str]:
        """Everyone who reviewed, claimed or holds a lease on the ticket."""
        people = {r.reviewer for r in ticket.reviews}
        people |= {lease.reviewer for lease in self.active_leases(ticket_id=ticket.ticket_id)}
        people |= {r for c in ticket.claims if (r := self.claims[c].resolver) is not None}
        return people

    def is_open(self, ticket: TicketSt) -> bool:
        return (ticket.status == "open" and ticket.honeypot is not True
                and not self.submissions[ticket.submission_id].closed)

    # --------------------------------------------------------------- apply
    def apply(self, entry: Entry) -> None:
        model = ev.PAYLOADS.get(entry.kind)
        self.seq = entry.seq
        if model is None:  # ingest events and others: not part of coordination
            return
        payload = model.model_validate(entry.payload)
        at = ev.parse_ts(entry.ts)
        handler = getattr(self, "_on_" + entry.kind.replace(".", "_"))
        handler(payload, at, entry)

    def _evidence(self, rid: str, rec: EvidenceRec) -> None:
        self.reviewers[rid].evidence.append(rec)

    def _on_coord_configured(self, p: ev.CoordConfigured, at: datetime, _: Entry) -> None:
        self.configured.append(p.params)

    def _on_reviewer_registered(self, p: ev.ReviewerRegistered, at: datetime, _: Entry) -> None:
        self.reviewers[p.reviewer] = ReviewerSt(p.reviewer, p.group, at, set(p.affiliation_tags))

    def _on_reviewer_affiliation_declared(self, p: ev.AffiliationDeclared, at: datetime,
                                          _: Entry) -> None:
        self.reviewers[p.reviewer].affiliation_tags.add(p.tag)

    def _on_reviewer_maintainer_appointed(self, p: ev.MaintainerAppointed, at: datetime,
                                          _: Entry) -> None:
        person = self.reviewers[p.reviewer]
        person.maintainer, person.maintainer_by = True, p.by

    def _on_reviewer_preferences_set(self, p: ev.PreferencesSet, at: datetime,
                                     _: Entry) -> None:
        person = self.reviewers[p.reviewer]
        person.pref_domains, person.pref_tiers, person.prefs_at = p.domains, p.tiers, at
        self.pref_changes[p.reviewer].append(at)
        # The current choice set was drawn for the old preferences.
        current = self.choice_sets.get(self.latest_set.get(p.reviewer, ""))
        if current is not None:
            current.consumed = True

    def _on_reviewer_maintainer_revoked(self, p: ev.MaintainerRevoked, at: datetime,
                                        _: Entry) -> None:
        person = self.reviewers[p.reviewer]
        person.maintainer, person.maintainer_by = False, None

    def _on_submission_opened(self, p: ev.SubmissionOpened, at: datetime, _: Entry) -> None:
        self.submissions[p.submission_id] = SubmissionSt(
            p.submission_id, p.title, p.repo_url, p.commit, p.lab_tag, p.authors, at,
            paper_ref=p.paper_ref, root=p.root)

    def _on_submission_basis_recorded(self, p: ev.BasisRecorded, at: datetime,
                                      _: Entry) -> None:
        self.submissions[p.submission_id].basis = p

    def _on_submission_closed(self, p: ev.SubmissionClosed, at: datetime, _: Entry) -> None:
        self.submissions[p.submission_id].closed = True

    def _on_submission_tagged(self, p: ev.SubmissionTagged, at: datetime, _: Entry) -> None:
        self.submissions[p.submission_id].tags = p.tags

    def _on_ticket_created(self, p: ev.TicketCreated, at: datetime, _: Entry) -> None:
        self.tickets[p.ticket_id] = TicketSt(
            p.ticket_id, p.submission_id, p.ticket_class, p.view, p.domain,
            float(p.difficulty), p.commitment, at, p.slots, paper=p.paper,
            tier=p.tier or tier_of(float(p.difficulty)))
        self.submissions[p.submission_id].tickets.append(p.ticket_id)

    def _on_discussion_posted(self, p: ev.DiscussionPosted, at: datetime, _: Entry) -> None:
        thread = (p.submission_id, p.declaration)
        self.posts[p.post_id] = PostSt(p.post_id, thread, p.author, p.kind, p.text,
                                       p.review_seq, at, ai_used=p.ai.used)
        self.threads[thread].append(p.post_id)
        if p.show_pseudonym:
            self.named[thread].add(p.author)

    def _on_discussion_voted(self, p: ev.DiscussionVoted, at: datetime, _: Entry) -> None:
        votes = self.posts[p.post_id].votes
        if p.value:
            votes[p.voter] = p.value
        else:
            votes.pop(p.voter, None)

    def _on_discussion_reported(self, p: ev.DiscussionReported, at: datetime,
                                _: Entry) -> None:
        self.posts[p.post_id].reports.append((p.reporter, p.reason))

    def _on_discussion_report_withdrawn(self, p: ev.ReportWithdrawn, at: datetime,
                                        _: Entry) -> None:
        post = self.posts[p.post_id]
        post.reports = [(r, why) for r, why in post.reports if r != p.reporter]

    def _on_discussion_thread_voted(self, p: ev.ThreadVoted, at: datetime, _: Entry) -> None:
        votes = self.thread_votes[(p.submission_id, p.declaration)]
        if p.value:
            votes[p.voter] = p.value
        else:
            votes.pop(p.voter, None)

    def _on_discussion_hidden(self, p: ev.DiscussionHidden, at: datetime, _: Entry) -> None:
        self.posts[p.post_id].hidden = p.reason

    def _on_ticket_reopen_requested(self, p: ev.ReopenRequested, at: datetime,
                                    _: Entry) -> None:
        self.reopens[p.request_id] = ReopenSt(p.request_id, p.ticket_id, p.post_id,
                                              p.requester, p.reason, at)

    def _on_ticket_reopen_resolved(self, p: ev.ReopenResolved, at: datetime, _: Entry) -> None:
        self.reopens[p.request_id].status = "reopened" if p.reopened else "dismissed"

    def _on_ticket_mapping_contested(self, p: ev.MappingContested, at: datetime,
                                     _: Entry) -> None:
        self.tickets[p.ticket_id].contests.append((p.reviewer, p.reason))

    def _on_ticket_round_opened(self, p: ev.RoundOpened, at: datetime, _: Entry) -> None:
        ticket = self.tickets[p.ticket_id]
        ticket.round, ticket.slots = p.round, p.slots

    def _on_choice_set_drawn(self, p: ev.ChoiceSetDrawn, at: datetime, _: Entry) -> None:
        self.choice_sets[p.set_id] = ChoiceSetSt(p.set_id, p.reviewer, p.tickets, at,
                                                 ev.parse_ts(p.expires_at),
                                                 preferences_applied=p.preferences_applied,
                                                 at_limit=p.at_limit)
        self.latest_set[p.reviewer] = p.set_id
        self.sets_drawn[p.reviewer].append(at)
        self.sets_of[p.reviewer].append(p.set_id)

    def _on_unit_shown(self, p: ev.UnitShown, at: datetime, _: Entry) -> None:
        self.seen_units[p.reviewer].add((p.submission_id, p.declaration))

    def _on_lease_granted(self, p: ev.LeaseGranted, at: datetime, _: Entry) -> None:
        lease = LeaseSt(p.lease_id, p.reviewer, p.duty, p.ticket_id, p.claim_id, p.set_id, at,
                        ev.parse_ts(p.expires_at), p.expected_s)
        self.leases[p.lease_id] = self.active[p.lease_id] = lease
        ticket = self.tickets[p.ticket_id]
        self.seen_units[p.reviewer].add((ticket.submission_id, ticket.view.declaration))
        if p.set_id is not None:
            self.choice_sets[p.set_id].consumed = True
            self.choice_sets[p.set_id].used = True

    def _on_lease_extended(self, p: ev.LeaseExtended, at: datetime, _: Entry) -> None:
        lease = self.leases[p.lease_id]
        lease.expires, lease.extended = ev.parse_ts(p.expires_at), True

    def _end_lease(self, lease_id: str, status: LeaseStatus) -> LeaseSt:
        lease = self.active.pop(lease_id)
        lease.status = status
        return lease

    def _unuse_set(self, lease: LeaseSt) -> None:
        """A ticket given up again leaves its set unused: otherwise taking and
        returning would be a reroll that no limit counts (C-32). This limits
        looks, not trust."""
        if lease.set_id is not None and lease.set_id in self.choice_sets:
            self.choice_sets[lease.set_id].used = False

    def _on_lease_returned(self, p: ev.LeaseEnded, at: datetime, _: Entry) -> None:
        self._unuse_set(self._end_lease(p.lease_id, "returned"))  # no penalty (SR-26)

    def _on_lease_cancelled(self, p: ev.LeaseEnded, at: datetime, _: Entry) -> None:
        self._end_lease(p.lease_id, "cancelled")

    def _on_lease_expired(self, p: ev.LeaseEnded, at: datetime, _: Entry) -> None:
        lease = self._end_lease(p.lease_id, "expired")
        self._unuse_set(lease)
        person = self.reviewers[lease.reviewer]  # reliability only, never trust (SR-27)
        person.reliability = person.reliability.lapsed()

    def _complete_lease(self, lease_id: str, at: datetime) -> LeaseSt:
        lease = self._end_lease(lease_id, "done")
        ticket = self.tickets[lease.ticket_id]
        bucket = difficulty_bucket(ticket.difficulty)
        self.durations[(lease.duty, bucket)].append(int((at - lease.granted).total_seconds()))
        person = self.reviewers[lease.reviewer]
        person.reliability = person.reliability.completed()
        return lease

    def _pair(self, a: str, b: str, at: datetime) -> None:
        if a != b:
            self.pairs[frozenset((a, b))] = at

    def _on_review_submitted(self, p: ev.ReviewSubmitted, at: datetime, entry: Entry) -> None:
        self._complete_lease(p.lease_id, at)
        ticket = self.tickets[p.ticket_id]
        rec = ReviewRec(entry.seq, at, p.lease_id, p.ticket_id, p.reviewer, p.duty, p.round,
                        p.verdict == "incorrect", p.reason, p.time_spent_s, float(p.t_factor),
                        p.roles, p.evidence, p.failed)
        for other in {r.reviewer for r in ticket.reviews}:
            self._pair(p.reviewer, other, at)
        ticket.reviews.append(rec)
        self.reviews[entry.seq] = rec
        if p.duty == "pvv":  # the PVV verdict is the reference for the pending reviews
            for seq in ticket.pvv_pending:
                target = self.reviews[seq]
                self._evidence(target.reviewer, EvidenceRec(
                    at, ticket.domain, target.incorrect, Source.PVV,
                    1.0 if rec.incorrect else 0.0, target.t_factor, ticket.ticket_id))
            ticket.pvv_pending.clear()
            ticket.pvv_for_decision = False

    def _on_pvv_requested(self, p: ev.PvvRequested, at: datetime, _: Entry) -> None:
        ticket = self.tickets[p.ticket_id]
        if p.review_seq is None:
            ticket.pvv_for_decision = True
            return
        reference = next((r for r in ticket.reviews if r.duty == "pvv"), None)
        if reference is None:
            ticket.pvv_pending.append(p.review_seq)
            return
        # A PVV verdict on this ticket exists already: compare right away (a PVV
        # cannot review the same ticket twice).
        target = self.reviews[p.review_seq]
        self._evidence(target.reviewer, EvidenceRec(
            at, ticket.domain, target.incorrect, Source.PVV,
            1.0 if reference.incorrect else 0.0, target.t_factor, ticket.ticket_id))

    def _on_claim_opened(self, p: ev.ClaimOpened, at: datetime, _: Entry) -> None:
        self.claims[p.claim_id] = ClaimSt(p.claim_id, p.ticket_id, p.claimant, p.review_seq, at)
        self.tickets[p.ticket_id].claims.append(p.claim_id)

    def _on_claim_resolved(self, p: ev.ClaimResolved, at: datetime, _: Entry) -> None:
        claim = self.claims[p.claim_id]
        claim.status = "confirmed" if p.confirmed else "rejected"
        claim.by, claim.resolver = p.by, p.resolver
        if p.lease_id is not None:
            self._complete_lease(p.lease_id, at)
        if p.resolver is not None:
            self._pair(p.resolver, claim.claimant, at)
        ticket = self.tickets[claim.ticket_id]
        if p.by == "honeypot":
            return  # the reveal carries the evidence
        source = Source.REFUTATION if p.by == "machine" else Source.PVV
        if p.confirmed and not ticket.error_confirmed:
            ticket.error_confirmed = True
            for r in ticket.reviews:  # a confirmed error is a hard anchor for every verdict
                self._evidence(r.reviewer, EvidenceRec(at, ticket.domain, r.incorrect, source,
                                                       1.0, r.t_factor, ticket.ticket_id))
        elif not p.confirmed:
            review = self.reviews[claim.review_seq]
            self._evidence(claim.claimant, EvidenceRec(at, ticket.domain, True, source, 0.0,
                                                       review.t_factor, ticket.ticket_id))

    def _on_ticket_decided(self, p: ev.TicketDecided, at: datetime, _: Entry) -> None:
        ticket = self.tickets[p.ticket_id]
        ticket.status, ticket.p_error, ticket.decided_at = p.outcome, float(p.p_error), at
        if p.outcome == "escalate" or ticket.error_confirmed:
            return
        if p.by == "maintainer":
            source, p_error = Source.PVV, 1.0 if p.outcome == "error" else 0.0
        else:  # consensus: weak evidence, w ≈ 0.2 (concept §6.2)
            source, p_error = Source.CONSENSUS, float(p.p_error)
        for r in ticket.reviews:
            self._evidence(r.reviewer, EvidenceRec(at, ticket.domain, r.incorrect, source,
                                                   p_error, r.t_factor, ticket.ticket_id))

    def _on_honeypots_revealed(self, p: ev.HoneypotsRevealed, at: datetime, _: Entry) -> None:
        for opening in p.openings:
            ticket = self.tickets[opening.ticket_id]
            ticket.honeypot = opening.honeypot
            if not opening.honeypot:
                if ticket.error_confirmed:  # a confirmed real error (anomaly signal, ADR 0006)
                    for r in ticket.reviews:
                        d = self.reviewers[r.reviewer].detections
                        self.reviewers[r.reviewer].detections = DetectionRecord(
                            d.honeypots_seen, d.honeypots_found, d.real_errors_seen + 1,
                            d.real_errors_found + int(r.incorrect))
                continue
            # Replace the soft evidence collected on this ticket by the hard one.
            for person in self.reviewers.values():
                person.evidence = [e for e in person.evidence
                                   if e.ticket_id != ticket.ticket_id]
            for r in ticket.reviews:
                self._evidence(r.reviewer, EvidenceRec(at, ticket.domain, r.incorrect,
                                                       Source.HONEYPOT, 1.0, r.t_factor,
                                                       ticket.ticket_id))
                d = self.reviewers[r.reviewer].detections
                self.reviewers[r.reviewer].detections = DetectionRecord(
                    d.honeypots_seen + 1, d.honeypots_found + int(r.incorrect),
                    d.real_errors_seen, d.real_errors_found)
            for claim_id in ticket.claims:
                claim = self.claims[claim_id]
                if claim.resolver is not None and claim.by == "pvv":
                    self._evidence(claim.resolver, EvidenceRec(
                        at, ticket.domain, claim.status == "confirmed", Source.HONEYPOT, 1.0,
                        1.0, ticket.ticket_id))


def difficulty_bucket(difficulty: float) -> int:
    """Lease durations are estimated per class and difficulty (SR-26)."""
    return -1 if difficulty < -0.5 else (1 if difficulty > 0.5 else 0)
