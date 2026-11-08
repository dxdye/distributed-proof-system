"""Axiom check (SR-02): every axiom outside Ax0 is a blocking finding."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

#: Ax0, the standard axioms of Lean 4 (concept §2.2).
STANDARD_AXIOMS: frozenset[str] = frozenset({"propext", "Classical.choice", "Quot.sound"})

AxiomKind = Literal["sorry", "native", "custom"]


@dataclass(frozen=True)
class AxiomFinding:
    axiom: str
    kind: AxiomKind
    blocking: bool = True

    @property
    def message(self) -> str:
        what = {
            "sorry": "the proof is incomplete (`sorry`)",
            "native": "the proof trusts the compiler (`native_decide` / `ofReduceBool`)",
            "custom": "the development postulates its own axiom",
        }[self.kind]
        return f"non-standard axiom {self.axiom}: {what}"


def classify_axiom(name: str) -> AxiomKind:
    if name == "sorryAx":
        return "sorry"
    # Lean <= 4.2x: Lean.ofReduceBool / Lean.trustCompiler.
    # Lean 4.3x: native_decide emits an auxiliary axiom `<decl>._native.native_decide.ax_…`.
    if name in ("Lean.ofReduceBool", "Lean.ofReduceNat", "Lean.trustCompiler") or (
        "._native." in name
    ):
        return "native"
    return "custom"


def check_axioms(axioms: Iterable[str]) -> list[AxiomFinding]:
    """Findings for all axioms outside Ax0, sorted by name."""
    return [
        AxiomFinding(name, classify_axiom(name))
        for name in sorted(set(axioms))
        if name not in STANDARD_AXIOMS
    ]
