"""Ticket and review records (interface I-3, SE §7).

Whether a ticket is a honeypot is *not* part of :class:`Ticket`: that flag lives
server-side only (see `dpc.honeypots.mixing.Slot`, SR-06).
"""

from __future__ import annotations

import secrets
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QUESTIONS_A = ("fidelity", "junk_values", "edge_cases", "vacuity", "quantifiers")


def new_ticket_id(ticket_class: str) -> str:
    """Random ids: neither their order nor their range reveals late-inserted
    honeypots (SR-06)."""
    return f"{ticket_class}-{secrets.token_hex(6)}"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PaperRef(_Model):
    doc: str
    loc: str
    mapped_by: str  # must not be the system that generated the proof (SR-24)
    contested: bool = False


class Ticket(_Model):
    ticket_id: str
    ticket_class: Literal["A", "B"] = Field(alias="class")
    commit: str
    declaration: str
    members: tuple[str, ...] = ()  # auxiliaries folded into this unit
    module: str | None = None
    domain: str | None = None
    source_lines: tuple[int, int] | None = None
    context: tuple[str, ...] = ()  # neighbouring units in the graph
    paper_ref: PaperRef | None = None
    questions: tuple[str, ...] = QUESTIONS_A
    difficulty_b: float = 0.0
    lens: str | None = None
    round: int = 1

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Evidence(_Model):
    """A Lean file backing an "incorrect" verdict (concept §5.2)."""

    type: Literal["lean"] = "lean"
    kind: Literal["vacuity", "trivialization", "definition_test_counterexample"]
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AIAssistance(_Model):
    """Declared AI use (SR-48)."""

    used: bool = False
    provider: str | None = None


class Review(_Model):
    ticket_id: str
    reviewer: str  # pseudonym (SR-23)
    verdict: Literal["correct", "incorrect"]
    reason: str = ""
    evidence: Evidence | None = None
    time_spent_s: int = Field(ge=0)
    ai: AIAssistance = AIAssistance()

    @model_validator(mode="after")
    def _justified(self) -> Review:
        """SR-09: an "incorrect" verdict without justification is rejected."""
        if self.verdict == "incorrect" and not self.reason.strip():
            raise ValueError("an 'incorrect' verdict needs a justification (SR-09)")
        if self.evidence is not None and self.verdict != "incorrect":
            raise ValueError("evidence only backs an 'incorrect' verdict")
        if self.ai.used and not self.ai.provider:
            raise ValueError("declared AI use must name the provider (SR-48)")
        return self

    @property
    def justified(self) -> bool:
        return self.verdict == "incorrect" and bool(self.reason.strip())
