"""Junk values of library functions a reviewer should know (concept §5, checklist).

Lean's libraries make functions total by fixing values where mathematics
leaves them undefined. A statement can then hold "for the wrong reason", or a
hypothesis can quietly include a point the paper excludes. The glossary shows
the note next to the constant. Every note names the Mathlib lemma that states
the value (checked against Mathlib's sources, 2026-11-14), so it can be
verified.
"""

from __future__ import annotations

NOTES: dict[str, str] = {
    "riemannZeta": "Mathlib gives ζ a value at the pole s = 1: "
                   "riemannZeta 1 = (γ − log(4π)) / 2 (lemma riemannZeta_one).",
    "Real.sqrt": "√x = 0 for every x ≤ 0 (Real.sqrt_eq_zero_of_nonpos).",
    "Real.log": "log 0 = 0 and log(−x) = log x (Real.log_zero, Real.log_neg_eq_log).",
    "Complex.log": "log 0 = 0 (Complex.log_zero).",
}


def note_for(name: str) -> str | None:
    return NOTES.get(name)
