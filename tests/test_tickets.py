"""Class-A tickets, reviews and static difficulty (SR-05, SR-09, SR-33, SR-48)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dpc.analysis import Analysis, assign_domains
from dpc.analysis.tcb import units
from dpc.tickets import (
    CoverageError,
    Review,
    Ticket,
    check_coverage,
    class_a_tickets,
    static_difficulty,
    static_features,
)

from conftest import DATA

COMMIT = "a" * 40


@pytest.mark.req("SR-05")
def test_every_tcb_new_declaration_lies_in_exactly_one_ticket(basic: Analysis) -> None:
    tickets = class_a_tickets(basic, COMMIT, assign_domains(basic))
    assert {t.declaration for t in tickets} == {u for u, x in units(basic).items() if x.in_tcb}
    assert all(t.ticket_class == "A" and t.commit == COMMIT for t in tickets)
    assert len({t.ticket_id for t in tickets}) == len(tickets)
    color = next(t for t in tickets if t.declaration == "Basic.Color")
    assert "Basic.Color.red" in color.members
    main = next(t for t in tickets if t.declaration == "Basic.main_theorem")
    assert "Basic.isEven" in main.context and "Basic.helper" not in main.context
    assert main.source_lines == (46, 49)


@pytest.mark.req("SR-05")
def test_coverage_check_detects_gaps_and_duplicates(basic: Analysis) -> None:
    tickets = class_a_tickets(basic, COMMIT)
    with pytest.raises(CoverageError, match="missing"):
        check_coverage(basic, tickets[1:])
    with pytest.raises(CoverageError, match="twice"):
        check_coverage(basic, [*tickets, tickets[0]])


def test_ticket_serialises_like_interface_i3(basic: Analysis) -> None:
    ticket = class_a_tickets(basic, COMMIT)[0]
    data = ticket.model_dump(by_alias=True)
    assert data["class"] == "A"
    assert "is_honeypot" not in data  # server-side only (SR-06)
    assert Ticket.model_validate(data) == ticket


@pytest.mark.req("SR-33")
def test_static_difficulty_orders_by_size_and_dependencies() -> None:
    analysis = Analysis.load(DATA / "basic" / "metadata.jsonl")
    tcb_units = {n: u for n, u in units(analysis).items() if u.in_tcb}
    features = static_features(analysis, tcb_units)
    assert features["Basic.main_theorem"].depth == 0
    assert features["Basic.double"].depth > 0
    b = static_difficulty(features)
    assert set(b) == set(tcb_units)
    assert b["Basic.main_theorem"] > b["Basic.secret"]  # many deps vs. an opaque Nat
    assert sum(b.values()) == pytest.approx(0.0, abs=0.01)  # standardised (values rounded)


@pytest.mark.req("SR-09")
def test_incorrect_without_justification_is_rejected() -> None:
    with pytest.raises(ValidationError, match="SR-09"):
        Review(ticket_id="A-1", reviewer="p1", verdict="incorrect", reason=" ", time_spent_s=60)
    ok = Review(ticket_id="A-1", reviewer="p1", verdict="incorrect",
                reason="force only smooth on [0, T*)", time_spent_s=1140)
    assert ok.justified
    assert not Review(ticket_id="A-1", reviewer="p1", verdict="correct", time_spent_s=5).justified


@pytest.mark.req("SR-48")
def test_ai_use_must_name_the_provider() -> None:
    with pytest.raises(ValidationError, match="SR-48"):
        Review.model_validate({"ticket_id": "A-1", "reviewer": "p", "verdict": "correct",
                               "time_spent_s": 1, "ai": {"used": True}})


def test_evidence_only_backs_incorrect() -> None:
    evidence = {"kind": "vacuity", "file_sha256": "0" * 64}
    with pytest.raises(ValidationError):
        Review.model_validate({"ticket_id": "A-1", "reviewer": "p", "verdict": "correct",
                               "time_spent_s": 1, "evidence": evidence})
