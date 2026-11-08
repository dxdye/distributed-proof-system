"""Class-A ticket generation (SR-05): one ticket for every unit of TCB_new."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from dpc.analysis.domains import DomainAssignment
from dpc.analysis.model import Analysis
from dpc.analysis.tcb import units as compute_units
from dpc.honeypots.mixing import new_ticket_id
from dpc.tickets.difficulty import static_difficulty, static_features
from dpc.tickets.model import Ticket


class CoverageError(ValueError):
    """Class A does not cover TCB_new exactly once (SR-05)."""


def class_a_tickets(
    analysis: Analysis,
    commit: str,
    domains: Mapping[str, DomainAssignment] | None = None,
    *,
    id_factory: Callable[[str], str] = new_ticket_id,
) -> list[Ticket]:
    all_units = compute_units(analysis)
    tcb_units = {n: u for n, u in all_units.items() if u.in_tcb}
    difficulty = static_difficulty(static_features(analysis, tcb_units))
    tickets = []
    for name, unit in sorted(tcb_units.items()):
        head = analysis.decls.get(name)
        neighbours = set()
        for member in unit.members:
            for dep in analysis.decls[member].tcb_deps:
                target = analysis.decls.get(dep)
                if target is not None and not target.hardened and target.unit != name:
                    neighbours.add(target.unit)
        lines = (head.range.start_line, head.range.end_line) if head and head.range else None
        tickets.append(Ticket.model_validate({
            "ticket_id": id_factory("A"),
            "class": "A",
            "commit": commit,
            "declaration": name,
            "members": unit.members,
            "module": unit.module,
            "domain": domains[name].domain if domains and name in domains else None,
            "source_lines": lines,
            "context": tuple(sorted(neighbours)),
            "difficulty_b": difficulty.get(name, 0.0),
        }))
    check_coverage(analysis, tickets)
    return tickets


def check_coverage(analysis: Analysis, tickets: Sequence[Ticket]) -> None:
    """Every TCB_new declaration lies in exactly one class-A ticket (SR-05)."""
    tcb_new = {d.name for d in analysis.decls.values() if d.in_tcb and not d.hardened}
    covered: dict[str, int] = {}
    for ticket in tickets:
        if ticket.ticket_class != "A":
            continue
        for member in ticket.members:
            covered[member] = covered.get(member, 0) + 1
    missing = sorted(tcb_new - covered.keys())
    double = sorted(m for m, n in covered.items() if n > 1)
    if missing or double:
        raise CoverageError(f"missing: {missing[:5]}, covered twice: {double[:5]}")
