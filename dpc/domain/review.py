"""PVV re-checks (concept §4, SR-13) and the IRT detection model (concept §8.2)."""

from __future__ import annotations

import math


def recheck_probability(
    kappa: float, *, incorrect: bool, ticket_class: str,
    rho_min: float = 0.05, rho_max: float = 0.5,
) -> float:
    """``ρ_u = ρ_min + (ρ_max − ρ_min)(1 − κ_u)``: new reviewers are checked
    often, proven ones rarely. Every "incorrect" in class A goes to a PVV."""
    if incorrect and ticket_class == "A":
        return 1.0
    kappa = min(1.0, max(0.0, kappa))
    return rho_min + (rho_max - rho_min) * (1 - kappa)


def detection_probability(ability: float, difficulty: float, discrimination: float = 1.0) -> float:
    """Item response model ``P(detect) = σ(a (θ − b))`` (concept §8.2, GLAD).
    The Beta model is the special case without item difficulty."""
    x = discrimination * (ability - difficulty)
    return 1 / (1 + math.exp(-x))
