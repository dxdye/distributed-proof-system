"""Trust model per person and domain (concept §6, SR-12).

Two rates per (person, domain), each with a Beta posterior:

* sensitivity ``s`` — probability of reporting an existing error,
* specificity ``c`` — probability of confirming something correct as correct.

Both are needed because the base rate is very skewed: someone who always
answers "correct" is right almost always, but has ``s ≈ 0``.

Every piece of evidence carries a probability ``p_error`` that the item was
erroneous and a weight. It updates ``s`` with weight ``w·p_error`` and ``c``
with weight ``w·(1 − p_error)``. This single rule covers all sources of
concept §6.2: honeypots and machine-checked refutations (``p_error = 1``,
``w = 1``), PVV re-checks (the PVV verdict as truth, ``w ≈ 0.5``) and consensus
(Dawid–Skene posterior ``π_i``, ``w ≈ 0.2``). Hard anchors count fully, soft
agreement weakly — trust cannot be built by mutual confirmation alone.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from scipy.stats import beta as beta_dist


@dataclass(frozen=True)
class BetaRate:
    """Beta(alpha, beta) posterior of a rate; Beta(1, 1) is the uniform prior."""

    alpha: float = 1.0
    beta: float = 1.0

    def update(self, success: bool, weight: float = 1.0) -> BetaRate:
        if weight < 0:
            raise ValueError("evidence weight must be non-negative")
        if success:
            return BetaRate(self.alpha + weight, self.beta)
        return BetaRate(self.alpha, self.beta + weight)

    def decay(self, lam: float, dt: float) -> BetaRate:
        """Pull the posterior back towards the prior (concept §6.3), so that no
        status is permanent: ``α ← 1 + λ^Δt (α − 1)``."""
        if not 0 < lam <= 1 or dt < 0:
            raise ValueError("need 0 < λ ≤ 1 and Δt ≥ 0")
        factor = lam**dt
        return BetaRate(1 + factor * (self.alpha - 1), 1 + factor * (self.beta - 1))

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def observations(self) -> float:
        return self.alpha + self.beta - 2

    def lower_bound(self, q: float = 0.05) -> float:
        """The q-quantile of the posterior (``LB_0.05`` in concept §6.3)."""
        return _beta_ppf(q, self.alpha, self.beta)


@lru_cache(maxsize=4096)
def _beta_ppf(q: float, alpha: float, beta: float) -> float:
    """The Beta quantile; pure, and costly enough in scipy to remember."""
    return float(beta_dist.ppf(q, alpha, beta))


class Source(Enum):
    """Where a piece of evidence comes from (concept §6.2)."""

    HONEYPOT = "honeypot"
    REFUTATION = "refutation"
    PVV = "pvv"
    CONSENSUS = "consensus"


#: Default weights (concept §6.2). Calibrated in the pilot.
DEFAULT_WEIGHTS: Mapping[Source, float] = {
    Source.HONEYPOT: 1.0,
    Source.REFUTATION: 1.0,
    Source.PVV: 0.5,
    Source.CONSENSUS: 0.2,
}


@dataclass(frozen=True)
class TrustState:
    """Trust of one person in one domain."""

    s: BetaRate = BetaRate()
    c: BetaRate = BetaRate()

    def kappa(self, q: float = 0.05) -> float:
        """Trust value ``κ = min(LB(s), LB(c))`` (concept §6.3)."""
        return min(self.s.lower_bound(q), self.c.lower_bound(q))

    def point_estimates(self) -> tuple[float, float]:
        return self.s.mean, self.c.mean

    def observe(self, said_incorrect: bool, p_error: float, weight: float) -> TrustState:
        """Update with a verdict on an item that is erroneous with probability
        ``p_error`` (see module docstring)."""
        if not 0.0 <= p_error <= 1.0:
            raise ValueError("p_error must be a probability")
        s, c = self.s, self.c
        if p_error > 0:
            s = s.update(success=said_incorrect, weight=weight * p_error)
        if p_error < 1:
            c = c.update(success=not said_incorrect, weight=weight * (1 - p_error))
        return TrustState(s, c)

    def decay(self, lam: float, dt: float) -> TrustState:
        return TrustState(self.s.decay(lam, dt), self.c.decay(lam, dt))


def record(
    state: TrustState,
    said_incorrect: bool,
    source: Source,
    *,
    p_error: float = 1.0,
    time_factor: float = 1.0,
    weights: Mapping[Source, float] = DEFAULT_WEIGHTS,
) -> TrustState:
    """Apply one piece of evidence. Honeypots and refutations imply
    ``p_error = 1``; ``time_factor`` down-weights hurried reviews (§9.3)."""
    if source in (Source.HONEYPOT, Source.REFUTATION):
        p_error = 1.0
    return state.observe(said_incorrect, p_error, weights[source] * time_factor)


def time_factor(seconds_spent: float, t_min: float) -> float:
    """``min(1, t / t_min)``: reviews faster than a plausible minimum reading
    time count less (concept §9.3, SR-29). Measuring beats enforcing."""
    if t_min <= 0:
        return 1.0
    return max(0.0, min(1.0, seconds_spent / t_min))


def external_prior(
    scores: Mapping[str, float],
    gammas: Mapping[str, float],
    a_max: float = 5.0,
) -> TrustState:
    """Capped prior from linked external profiles (concept §6.5, SR-41):
    ``α₀ = 1 + min(Σ γ_q log(1 + score_q), a_max)``, ``β₀ = 1``. With
    ``a_max ≈ 5`` a strong profile counts like five passed honeypots."""
    boost = sum(gammas.get(q, 0.0) * math.log1p(max(0.0, v)) for q, v in scores.items())
    alpha0 = 1.0 + min(boost, a_max)
    return TrustState(BetaRate(alpha0, 1.0), BetaRate(alpha0, 1.0))


@dataclass(frozen=True)
class RoleThresholds:
    theta_pv: float = 0.5
    theta_pvv: float = 0.75

    def roles(self, state: TrustState) -> frozenset[str]:
        """Roles in one domain (concept §6.3); maintainers are appointed."""
        kappa = state.kappa()
        roles = set()
        if kappa >= self.theta_pv:
            roles.add("PV")
        if kappa >= self.theta_pvv:
            roles.add("PVV")
        return frozenset(roles)
