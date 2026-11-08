"""Domain assignment for class-A units (SR-04).

Heuristic: a unit belongs to the domain of the hardened library code its
statement builds on, e.g. a definition using ``Mathlib.Analysis.*`` belongs to
analysis. Units without such evidence inherit the majority domain of the new
units they depend on. Maintainer overrides always win; reviewers can later
re-route tickets to another domain (concept §9.4), which feeds back here.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from dpc.analysis.model import Analysis
from dpc.analysis.tcb import units

#: Longest-prefix map from library module to domain. ``None`` = no evidence
#: (generic infrastructure such as core or ``Mathlib.Data``).
DEFAULT_MODULE_DOMAINS: Mapping[str, str | None] = {
    "Mathlib.Analysis": "analysis",
    "Mathlib.MeasureTheory": "analysis",
    "Mathlib.Topology": "topology",
    "Mathlib.NumberTheory": "number_theory",
    "Mathlib.Algebra": "algebra",
    "Mathlib.RingTheory": "algebra",
    "Mathlib.GroupTheory": "algebra",
    "Mathlib.FieldTheory": "algebra",
    "Mathlib.LinearAlgebra": "algebra",
    "Mathlib.RepresentationTheory": "algebra",
    "Mathlib.AlgebraicGeometry": "algebraic_geometry",
    "Mathlib.Geometry": "geometry",
    "Mathlib.Combinatorics": "combinatorics",
    "Mathlib.Probability": "probability",
    "Mathlib.CategoryTheory": "category_theory",
    "Mathlib.SetTheory": "logic",
    "Mathlib.Logic": "logic",
    "Mathlib.ModelTheory": "logic",
    "Mathlib.Computability": "logic",
    "Mathlib.Order": "order",
    "Mathlib.Data": None,
    "Mathlib.Tactic": None,
}

Source = Literal["override", "library", "inherited", "unassigned"]


@dataclass(frozen=True)
class DomainAssignment:
    domain: str | None
    source: Source
    evidence: Mapping[str, int] = field(default_factory=dict)


def _domain_of_module(module: str | None, table: Mapping[str, str | None]) -> str | None:
    if module is None:
        return None
    best: tuple[int, str | None] = (-1, None)
    for prefix, domain in table.items():
        if (module == prefix or module.startswith(prefix + ".")) and len(prefix) > best[0]:
            best = (len(prefix), domain)
    return best[1]


def _majority(votes: Counter[str]) -> str | None:
    if not votes:
        return None
    top = max(votes.values())
    return sorted(d for d, n in votes.items() if n == top)[0]


def assign_domains(
    analysis: Analysis,
    overrides: Mapping[str, str] | None = None,
    module_domains: Mapping[str, str | None] = DEFAULT_MODULE_DOMAINS,
) -> dict[str, DomainAssignment]:
    decls = analysis.decls
    tcb_units = {name: u for name, u in units(analysis).items() if u.in_tcb}
    result: dict[str, DomainAssignment] = {}
    unit_deps: dict[str, set[str]] = {}

    for name, unit in tcb_units.items():
        votes: Counter[str] = Counter()
        deps: set[str] = set()
        for member in unit.members:
            for dep in decls[member].tcb_deps:
                target = decls.get(dep)
                if target is None:
                    continue
                if target.hardened:
                    domain = _domain_of_module(target.module, module_domains)
                    if domain:
                        votes[domain] += 1
                elif target.unit != name:
                    deps.add(target.unit)
        unit_deps[name] = deps
        if overrides and name in overrides:
            result[name] = DomainAssignment(overrides[name], "override")
        elif votes:
            result[name] = DomainAssignment(_majority(votes), "library", dict(votes))

    # Propagate along new dependencies until nothing changes.
    changed = True
    while changed:
        changed = False
        for name in tcb_units:
            if name in result:
                continue
            votes = Counter(
                d
                for dep in unit_deps[name]
                if (a := result.get(dep)) is not None and (d := a.domain) is not None
            )
            if votes:
                result[name] = DomainAssignment(_majority(votes), "inherited", dict(votes))
                changed = True

    for name in tcb_units:
        result.setdefault(name, DomainAssignment(None, "unassigned"))
    return dict(sorted(result.items()))
