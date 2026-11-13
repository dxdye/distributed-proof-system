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


class MaintainerAppointed(_P):
    reviewer: str
    #: ``operator``: by command line (OD-2); ``identity_provider``: the role is
    #: managed in the identity provider and was granted there (docs/adr/0010).
    by: Literal["operator", "identity_provider"] = "operator"


class MaintainerRevoked(_P):
    reviewer: str
    by: Literal["operator", "identity_provider"]


class SubmissionOpened(_P):
    submission_id: str
    title: str
    repo_url: str
    commit: str
    artifact_key: str | None = None
    lab_tag: Hex64 | None = None
    authors: tuple[str, ...] = ()  # reviewer ids of the authors (SR-08)


class TicketCreated(_P):
    ticket_id: str
    submission_id: str
    ticket_class: Literal["A"]
    view: UnitView
    domain: str
    difficulty: Dec
    slots: int  # parallel review slots of round 1 (SR-28)
    commitment: Hex64  # SHA-256 of the honeypot opening (SR-37)


class ChoiceSetDrawn(_P):
    set_id: str
    reviewer: str
    tickets: tuple[str, ...]
    expires_at: Ts


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


PAYLOADS: dict[str, type[_P]] = {
    "coord.configured": CoordConfigured,
    "reviewer.registered": ReviewerRegistered,
    "reviewer.affiliation_declared": AffiliationDeclared,
    "reviewer.maintainer_appointed": MaintainerAppointed,
    "reviewer.maintainer_revoked": MaintainerRevoked,
    "submission.opened": SubmissionOpened,
    "submission.closed": SubmissionClosed,
    "ticket.created": TicketCreated,
    "ticket.round_opened": RoundOpened,
    "ticket.decided": TicketDecided,
    "choice_set.drawn": ChoiceSetDrawn,
    "lease.granted": LeaseGranted,
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
