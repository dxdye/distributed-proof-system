"""Ticket units, TCB_new, B(T) and graph measures (SR-03, concept §2, §7.1).

A *unit* is what one ticket covers: a user-facing declaration together with
the auxiliaries the analyzer folded into it (constructors, matchers, …).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from dpc.analysis.axioms import AxiomFinding, check_axioms
from dpc.analysis.model import Analysis, Decl


@dataclass(frozen=True)
class Unit:
    name: str
    display_name: str
    decl_kind: str
    module: str | None
    members: tuple[str, ...]
    in_tcb: bool
    lines: int | None

    @property
    def ticket_class(self) -> str:
        """Class A (trusted computing base) or B (proof internals), concept §3."""
        return "A" if self.in_tcb else "B"


def units(analysis: Analysis) -> dict[str, Unit]:
    """Group all non-hardened declarations into ticket units."""
    groups: dict[str, list[Decl]] = defaultdict(list)
    for decl in analysis.decls.values():
        if not decl.hardened:
            groups[decl.unit].append(decl)
    result: dict[str, Unit] = {}
    for name, members in sorted(groups.items()):
        head = analysis.decls.get(name) or members[0]
        result[name] = Unit(
            name=name,
            display_name=head.display_name,
            decl_kind=head.decl_kind,
            module=head.module,
            members=tuple(sorted(m.name for m in members)),
            in_tcb=any(m.in_tcb for m in members),
            lines=head.range.lines if head.range else None,
        )
    return result


def closure(decls: Mapping[str, Decl], start: Iterable[str], *, tcb_only: bool) -> set[str]:
    """Names reachable from ``start`` along TCB edges (or all edges).

    Edges to declarations that were not exported are ignored; for the hardened
    frontier of ``Dep(T)`` the analyzer deliberately does not expand further.
    """
    seen: set[str] = set()
    todo = deque(start)
    while todo:
        name = todo.popleft()
        if name in seen:
            continue
        seen.add(name)
        decl = decls.get(name)
        if decl is None:
            continue
        deps = decl.tcb_deps if tcb_only else (decl.all_deps or decl.tcb_deps)
        todo.extend(d for d in deps if d not in seen)
    return seen


def reverse_degree(analysis: Analysis) -> dict[str, int]:
    """deg⁻ per unit: number of *other* units that use it (concept §7.1)."""
    decls = analysis.decls
    users: dict[str, set[str]] = defaultdict(set)
    for decl in decls.values():
        if decl.hardened:
            continue
        for dep in decl.all_deps or decl.tcb_deps:
            target = decls.get(dep)
            if target is not None and not target.hardened and target.unit != decl.unit:
                users[target.unit].add(decl.unit)
    return {u: len(users.get(u, ())) for u in units(analysis)}


@dataclass(frozen=True)
class Summary:
    root: str
    toolchain: str
    axioms: tuple[str, ...]
    findings: tuple[AxiomFinding, ...]
    tcb_decls: int
    tcb_new_decls: int
    tcb_new_units: tuple[str, ...]
    tcb_new_lines: int | None
    b_new_units: tuple[str, ...]
    hardened_in_tcb: int

    @property
    def blocking(self) -> bool:
        return any(f.blocking for f in self.findings)

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "toolchain": self.toolchain,
            "axioms": list(self.axioms),
            "findings": [
                {"axiom": f.axiom, "kind": f.kind, "blocking": f.blocking} for f in self.findings
            ],
            "tcb_decls": self.tcb_decls,
            "tcb_new_decls": self.tcb_new_decls,
            "tcb_new_units": len(self.tcb_new_units),
            "tcb_new_lines": self.tcb_new_lines,
            "b_new_units": len(self.b_new_units),
            "hardened_in_tcb": self.hardened_in_tcb,
        }


def summarize(analysis: Analysis) -> Summary:
    decls = analysis.decls.values()
    all_units = units(analysis)
    tcb_units = tuple(u.name for u in all_units.values() if u.in_tcb)
    lines = [all_units[u].lines for u in tcb_units]
    return Summary(
        root=analysis.header.root,
        toolchain=analysis.header.toolchain,
        axioms=analysis.header.axioms,
        findings=tuple(check_axioms(analysis.header.axioms)),
        tcb_decls=sum(1 for d in decls if d.in_tcb),
        tcb_new_decls=sum(1 for d in decls if d.in_tcb and not d.hardened),
        tcb_new_units=tcb_units,
        tcb_new_lines=None if any(n is None for n in lines) else sum(n or 0 for n in lines),
        b_new_units=tuple(u.name for u in all_units.values() if not u.in_tcb),
        hardened_in_tcb=sum(1 for d in decls if d.in_tcb and d.hardened),
    )
