"""Graph diff between two commits (SR-16; groundwork for the semantic diff, SR-55).

A ticket (unit) must be invalidated exactly when its own meaning or the meaning
of something in its TCB changed. Proof-only changes are re-checked by the
kernel at build time and invalidate no class-A ticket; they are reported
separately because they matter for class B (comparison with the paper).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dpc.analysis.model import Analysis, Decl
from dpc.analysis.tcb import closure, units


@dataclass(frozen=True)
class GraphDiff:
    added: frozenset[str]
    removed: frozenset[str]
    meaning_changed: frozenset[str]  # declarations
    proof_only_changed: frozenset[str]  # declarations (theorems)
    invalidated_units: frozenset[str]  # tickets to re-open (new commit's units)
    kept_units: frozenset[str]  # decisions carried over unchanged

    def as_dict(self) -> dict[str, list[str]]:
        return {k: sorted(getattr(self, k)) for k in self.__dataclass_fields__}


def _changed(old: Mapping[str, Decl], new: Mapping[str, Decl]) -> tuple[set[str], set[str]]:
    meaning, proof_only = set(), set()
    for name in old.keys() & new.keys():
        o, n = old[name], new[name]
        if o.meaning_hash != n.meaning_hash:
            meaning.add(name)
        elif o.proof_hash != n.proof_hash:
            proof_only.add(name)
    return meaning, proof_only


def graph_diff(old: Analysis, new: Analysis) -> GraphDiff:
    added = set(new.decls) - set(old.decls)
    removed = set(old.decls) - set(new.decls)
    meaning, proof_only = _changed(old.decls, new.decls)
    dirty = meaning | added

    invalidated: set[str] = set()
    new_units = units(new)
    old_units = units(old)
    for unit in new_units.values():
        reach = closure(new.decls, unit.members, tcb_only=True)
        previous = old_units.get(unit.name)
        if (
            reach & dirty
            or previous is None
            or previous.in_tcb != unit.in_tcb  # moved between class A and B
            or previous.members != unit.members
        ):
            invalidated.add(unit.name)
    return GraphDiff(
        added=frozenset(added),
        removed=frozenset(removed),
        meaning_changed=frozenset(meaning),
        proof_only_changed=frozenset(proof_only),
        invalidated_units=frozenset(invalidated),
        kept_units=frozenset(set(new_units) - invalidated),
    )
