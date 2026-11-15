"""Junk values of library functions a reviewer should know (concept §5, checklist).

Lean's libraries make functions total by fixing values where mathematics
leaves them undefined. A statement can then hold "for the wrong reason", or a
hypothesis can quietly include a point the paper excludes. The glossary shows
the note next to the constant. Every note names the Mathlib lemma that states
the value (checked against Mathlib's sources, 2026-11-14), so it can be
verified. The notes are applied when a ticket is served
(:func:`dpc.tickets.library.annotate_view`), so views rendered earlier get
new notes too.
"""

from __future__ import annotations

_ORDER = ("The order n lies in WithTop ℕ∞: ∞ = ↑(⊤ : ℕ∞) means smooth (contDiff_infty), "
          "ω = ⊤ means analytic (Mathlib.Analysis.Calculus.ContDiff.Defs). A bare ⊤ here is "
          "ω, not ∞.")

NOTES: dict[str, str] = {
    "riemannZeta": "Mathlib gives ζ a value at the pole s = 1: "
                   "riemannZeta 1 = (γ − log(4π)) / 2 (lemma riemannZeta_one).",
    "Real.sqrt": "√x = 0 for every x ≤ 0 (Real.sqrt_eq_zero_of_nonpos).",
    "Real.log": "log 0 = 0 and log(−x) = log x (Real.log_zero, Real.log_neg_eq_log).",
    "Complex.log": "log 0 = 0 (Complex.log_zero).",
    # Checked against Mathlib d13f23b7 (openai/math), 2026-11-14:
    "ContDiff": _ORDER,
    "ContDiffOn": _ORDER,
    "ContDiffAt": _ORDER,
    "ContDiffWithinAt": _ORDER,
    "ENNReal.toReal": "∞.toReal = 0 (ENNReal.toReal_top).",
    "ENNReal.ofReal": "ofReal p = 0 for every p ≤ 0 (ENNReal.ofReal_eq_zero).",
    "fderiv": "fderiv 𝕜 f x = 0 where f is not differentiable at x "
              "(fderiv_zero_of_not_differentiableAt).",
    "deriv": "deriv f x = 0 where f is not differentiable at x "
             "(deriv_zero_of_not_differentiableAt).",
    "derivWithin": "derivWithin f s x = 0 where f is not differentiable within s at x "
                   "(derivWithin_zero_of_not_differentiableWithinAt).",
    "gradient": "∇ f x = 0 where f is not differentiable at x "
                "(gradient_eq_zero_of_not_differentiableAt).",
    "MeasureTheory.integral": "∫ f = 0 when f is not integrable "
                              "(MeasureTheory.integral_undef).",
    "MeasureTheory.MemLp": "For p = 0 it holds for every a.e. strongly measurable f "
                           "(MeasureTheory.memLp_zero_iff_aestronglyMeasurable).",
    # Checked against Lean 4.34.1 and Mathlib d13f23b7, 2026-11-15:
    "Nat.Coprime": "Coprime m n means gcd m n = 1. Since gcd 0 n = n, 0 is coprime only to "
                   "1 (Nat.coprime_zero_left): it matters for windows that contain 0.",
    "Nat.primeFactors": "0 and 1 have no prime factors: primeFactors 0 = primeFactors 1 = ∅ "
                        "(Nat.primeFactors_zero, Nat.primeFactors_one).",
}


def note_for(name: str) -> str | None:
    return NOTES.get(name)
