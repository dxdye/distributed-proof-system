"""Events of the coordination service (docs/adr/0008).

Every state change is one of these events in the audit log; the service state
is a projection of the log (`dpc.coord.state`). Payloads are validated on
append *and* on replay. Floats are stored as decimal strings (canonical JSON
has none, ADR 0002).

Privacy (SR-23): the log never contains pseudonyms or affiliations in clear.
Reviewers appear as random ids (``R-…``); affiliations and the submitting lab
as keyed hashes, so the exclusion rule of SR-50 can be evaluated from the log
by whoever holds the key, and by nobody else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dpc.audit.log import format_ts
from dpc.tickets.model import AIAssistance, Evidence
from dpc.tickets.paper import PaperPassage
from dpc.tickets.views import UnitView

Dec = Annotated[str, Field(pattern=r"^-?[0-9]+(\.[0-9]+)?(e[-+]?[0-9]+)?$")]
Ts = Annotated[str, Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")]
Hex64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Group = Literal["expert", "doctoral", "student", "other"]
Duty = Literal["review", "pvv", "claim"]


def dec(x: float) -> str:
    return format(float(x), ".9g")


def ts(moment: datetime) -> str:
    return format_ts(moment)


def parse_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoordConfigured(_P):
    params: dict[str, Any]


class ReviewerRegistered(_P):
    reviewer: str
    group: Group
    affiliation_tags: tuple[Hex64, ...] = ()
    notice: str  # version of the registration notice (training-data use, SR-49)


class AffiliationDeclared(_P):
    reviewer: str
    tag: Hex64


class AdminAppointed(_P):
    """An administrator of the platform (proposal C-42). Older logs record the
    same as ``reviewer.maintainer_appointed``: the former single maintainer
    role is the administrator now."""

    reviewer: str
    #: ``operator``: by command line (OD-2); ``identity_provider``: the role is
    #: managed in the identity provider and was granted there (docs/adr/0010).
    by: Literal["operator", "identity_provider"] = "operator"


class PreferencesSet(_P):
    """What a reviewer wants to work on. It only raises the chance that such
    tickets are offered; it never decides coverage (SR-32, SR-39)."""

    reviewer: str
    domains: tuple[str, ...] = ()
    tiers: tuple[Literal["easy", "medium", "hard", "excellence"], ...] = ()


class AdminRevoked(_P):
    reviewer: str
    by: Literal["operator", "identity_provider"]


class RootAppointed(_P):
    """A root tester: every role, free of the rules. Effective only where the
    parameters allow root accounts (test systems, never production)."""

    reviewer: str


class RootRevoked(_P):
    reviewer: str


class MaintainerRoleAppointed(_P):
    """A maintainer of some domains (C-42), appointed by an administrator with
    a reason and an end date. Only someone who is PVV in each of the domains
    may be appointed, unless as *founding* maintainer: then, until the end
    date, they count as PVV there (the cold start of a new installation)."""

    reviewer: str
    domains: tuple[str, ...]
    by: str  # the administrator
    reason: str
    until: Ts  # end of the term (ev.ts)
    founding: bool = False


class MaintainerRoleRevoked(_P):
    reviewer: str
    domains: tuple[str, ...]
    by: str  # the administrator
    reason: str


class SubmissionOpened(_P):
    submission_id: str
    title: str
    repo_url: str
    commit: str
    artifact_key: str | None = None
    lab_tag: Hex64 | None = None
    authors: tuple[str, ...] = ()  # reviewer ids of the authors (SR-08)
    paper_ref: str | None = None  # the submission's reference to its paper
    root: str | None = None  # the main theorem (progress page, PRL 2)


class TicketCreated(_P):
    ticket_id: str
    submission_id: str
    ticket_class: Literal["A"]
    view: UnitView
    domain: str
    difficulty: Dec
    slots: int  # parallel review slots of round 1 (SR-28)
    commitment: Hex64  # SHA-256 of the honeypot opening (SR-37)
    #: The paper passage this declaration formalises (SR-24); None: not mapped yet.
    paper: PaperPassage | None = None
    #: Absolute difficulty tier (dpc.coord.tiers); None in older logs.
    tier: Literal["easy", "medium", "hard", "excellence"] | None = None


class DiscussionPosted(_P):
    """A post in the thread of a declaration (C-25): a shared review of the
    author's own or a comment. Only after the declaration is decided."""

    post_id: str
    submission_id: str
    declaration: str
    author: str
    kind: Literal["review", "comment"]
    text: str = ""
    review_seq: int | None = None  # kind "review": the shared review
    show_pseudonym: bool = False  # per thread: the author's pseudonym instead of a letter
    ai: AIAssistance = AIAssistance()


class DiscussionVoted(_P):
    """Sorts posts only; never enters trust, roles or decisions (S-22)."""

    post_id: str
    voter: str
    value: Literal[-1, 0, 1]


class ThreadVoted(_P):
    """Whether a discussion is worth reading: sorts the list of discussions.
    It says nothing about the decision and never enters trust, roles or
    decisions (S-22)."""

    submission_id: str
    declaration: str
    voter: str
    value: Literal[-1, 0, 1]


class DiscussionReported(_P):
    post_id: str
    reporter: str
    reason: str


class ReportWithdrawn(_P):
    post_id: str
    reporter: str


class DiscussionHidden(_P):
    post_id: str
    by: str  # maintainer
    reason: str


class ReopenRequested(_P):
    """A post says a decided declaration is wrong after all (C-25)."""

    request_id: str
    ticket_id: str
    post_id: str | None = None
    requester: str
    reason: str


class ReopenResolved(_P):
    request_id: str
    by: str  # maintainer
    reopened: bool
    reason: str


class MappingContested(_P):
    """A reviewer says the paper passage does not belong to the declaration
    (SR-24). Maintainers see every contest."""

    ticket_id: str
    reviewer: str
    reason: str


class ChoiceSetDrawn(_P):
    set_id: str
    reviewer: str
    tickets: tuple[str, ...]
    expires_at: Ts
    #: The reviewer's preferences could be used for this set (C-22). Never
    #: why not: that would tell which papers have such tickets.
    preferences_applied: bool = False
    #: Drawn while the reviewer held as many tickets as allowed: shown, but no
    #: ticket could be taken from it, so it never counts as unused (C-32).
    at_limit: bool = False


class UnitShown(_P):
    """A reviewer unfolded another declaration of the submission and saw it in
    the original (C-39). From then on it is not offered to them as a ticket:
    with the original in mind, its planted copy could be told apart by
    comparison instead of by mathematics."""

    reviewer: str
    submission_id: str
    declaration: str


class LeaseGranted(_P):
    lease_id: str
    reviewer: str
    duty: Duty
    ticket_id: str
    claim_id: str | None = None
    set_id: str | None = None
    expires_at: Ts
    expected_s: int


class LeaseExtended(_P):
    lease_id: str
    expires_at: Ts


class LeaseEnded(_P):
    """Payload of ``lease.returned``, ``lease.expired`` and ``lease.cancelled``."""

    lease_id: str


class ReviewSubmitted(_P):
    lease_id: str
    ticket_id: str
    reviewer: str
    duty: Literal["review", "pvv"]
    round: int
    verdict: Literal["correct", "incorrect"]
    reason: str
    #: Checklist questions an "incorrect" verdict says fail (empty in older logs).
    failed: tuple[str, ...] = ()
    evidence: Evidence | None = None
    ai: AIAssistance = AIAssistance()
    time_spent_s: int
    t_factor: Dec  # min(1, t / t_min(i)) (SR-29)
    roles: tuple[str, ...]  # roles in the ticket's domain when submitted


class PvvRequested(_P):
    ticket_id: str
    review_seq: int | None = None  # the review to compare with; None: needed for the decision
    reason: Literal["sample", "decision"]


class ClaimOpened(_P):
    claim_id: str
    ticket_id: str
    claimant: str
    review_seq: int


class ClaimResolved(_P):
    claim_id: str
    confirmed: bool
    by: Literal["pvv", "machine", "maintainer", "honeypot"]
    resolver: str | None = None
    lease_id: str | None = None
    reason: str = ""


class RoundOpened(_P):
    ticket_id: str
    round: int
    slots: int  # review slots in total so far


class TicketDecided(_P):
    ticket_id: str
    outcome: Literal["accepted", "error", "escalate"]
    p_error: Dec
    independent_votes: int
    by: Literal["rule", "maintainer"] = "rule"
    maintainer: str | None = None
    reason: str = ""


class Opening(_P):
    """Opens the commitment of one ticket."""

    ticket_id: str
    honeypot: bool
    salt: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    mutant_hash: str | None = None
    operator: str | None = None
    source: str | None = None


class HoneypotsRevealed(_P):
    submission_id: str | None = None  # None: a batch across submissions
    final: bool = False  # True: all remaining commitments at closing
    openings: tuple[Opening, ...]


class SubmissionClosed(_P):
    submission_id: str


class SubmissionTagged(_P):
    """The hashtags of a submission, set by a maintainer (proposal C-44): the
    whole set, replacing the previous one. They name the problem (`navier-stokes`,
    `erdos-problems`, `counterexample`) so that it is found quickly on the
    progress page and in the discussions. They are not a preference for the
    draw: a tag can name a single paper, and choosing tickets by paper would
    allow targeting them (C-32)."""

    submission_id: str
    tags: tuple[str, ...]


class LibraryRef(_P):
    name: str
    url: str
    rev: str


class BasisRecorded(_P):
    """What the result relies on (proposal C-29), from the submission's ingest:
    what the kernel re-checked, and what is trusted without re-checking."""

    submission_id: str
    toolchain: str
    axioms: tuple[str, ...]  # of the main theorem; only Ax0 is admitted
    libraries: tuple[LibraryRef, ...] = ()  # official packages at their pinned revisions
    hardened_files: int | None = None  # compared before and after the build
    hardened_unchanged: bool | None = None
    replayed: bool = False  # the kernel replay of ADR 0009 ran
    modules_replayed: int = 0
    constants_replayed: int = 0
    replay_failures: int = 0
    modules_trusted: int = 0  # official packages, trusted by location
    modules_core: int = 0  # the toolchain's library
    libraries_replayed: bool = False  # official packages re-checked as well (C-29)
    second_kernel: bool = False  # an independent kernel re-checked (C-29)


PAYLOADS: dict[str, type[_P]] = {
    "coord.configured": CoordConfigured,
    "reviewer.registered": ReviewerRegistered,
    "reviewer.affiliation_declared": AffiliationDeclared,
    "reviewer.admin_appointed": AdminAppointed,
    "reviewer.admin_revoked": AdminRevoked,
    # The same, as older logs name it (before C-42 the administrator was "maintainer").
    "reviewer.maintainer_appointed": AdminAppointed,
    "reviewer.maintainer_revoked": AdminRevoked,
    "reviewer.root_appointed": RootAppointed,
    "reviewer.root_revoked": RootRevoked,
    "role.maintainer_appointed": MaintainerRoleAppointed,
    "role.maintainer_revoked": MaintainerRoleRevoked,
    "reviewer.preferences_set": PreferencesSet,
    "ticket.mapping_contested": MappingContested,
    "discussion.posted": DiscussionPosted,
    "discussion.voted": DiscussionVoted,
    "discussion.reported": DiscussionReported,
    "discussion.report_withdrawn": ReportWithdrawn,
    "discussion.thread_voted": ThreadVoted,
    "discussion.hidden": DiscussionHidden,
    "ticket.reopen_requested": ReopenRequested,
    "ticket.reopen_resolved": ReopenResolved,
    "submission.opened": SubmissionOpened,
    "submission.closed": SubmissionClosed,
    "submission.tagged": SubmissionTagged,
    "submission.basis_recorded": BasisRecorded,
    "ticket.created": TicketCreated,
    "ticket.round_opened": RoundOpened,
    "ticket.decided": TicketDecided,
    "choice_set.drawn": ChoiceSetDrawn,
    "lease.granted": LeaseGranted,
    "unit.shown": UnitShown,
    "lease.extended": LeaseExtended,
    "lease.returned": LeaseEnded,
    "lease.expired": LeaseEnded,
    "lease.cancelled": LeaseEnded,
    "review.submitted": ReviewSubmitted,
    "pvv.requested": PvvRequested,
    "claim.opened": ClaimOpened,
    "claim.resolved": ClaimResolved,
    "honeypots.revealed": HoneypotsRevealed,
}
