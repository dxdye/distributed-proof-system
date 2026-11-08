"""Monte Carlo hardening of the proof internals (concept §7; SR-14, SR-15).

Declarations of ``B(T)`` are drawn with probability ``π_d ∝ w_d``,
``w_d = (1 + deg⁻(d))^γ · h_d`` (``h_d``: origin factor, AI-generated > human-
reviewed). If ``n`` checks with detection probability ``q`` find nothing, the
weighted error mass satisfies, with confidence ``1 − δ``::

    ε_w ≤ ln(1/δ) / (q n)

``q`` is estimated from class-B honeypots; conservatively its lower
Clopper–Pearson bound is used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
from scipy.stats import beta as beta_dist


def draw_weights(
    deg_minus: Mapping[str, int], origin: Mapping[str, float] | None = None, gamma: float = 1.0
) -> dict[str, float]:
    """Normalised drawing probabilities ``π_d`` (every one is logged, SR-14)."""
    origin = origin or {}
    raw = {d: (1 + n) ** gamma * origin.get(d, 1.0) for d, n in deg_minus.items()}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("no positive weights")
    return {d: w / total for d, w in sorted(raw.items())}


def draw(pi: Mapping[str, float], n: int, rng: np.random.Generator) -> list[str]:
    """``n`` draws with replacement according to ``π``."""
    names = list(pi)
    probs = np.array([pi[d] for d in names])
    return [names[i] for i in rng.choice(len(names), size=n, p=probs / probs.sum())]


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Two one-sided (1 − α) bounds for a binomial proportion."""
    if not 0 <= k <= n:
        raise ValueError("need 0 ≤ k ≤ n")
    lower = 0.0 if k == 0 else float(beta_dist.ppf(alpha, k, n - k + 1))
    upper = 1.0 if k == n else float(beta_dist.ppf(1 - alpha, k + 1, n - k))
    return lower, upper


def certificate_bound(n_checks: int, q: float, delta: float = 0.05) -> float:
    """Upper bound on the weighted error mass after ``n`` clean checks."""
    if n_checks <= 0 or q <= 0:
        return 1.0
    return min(1.0, math.log(1 / delta) / (q * n_checks))


def checks_needed(epsilon: float, q: float, delta: float = 0.05) -> int:
    """Inverse: checks needed for a target bound ``ε_w`` (planning, concept §9)."""
    return math.ceil(math.log(1 / delta) / (q * epsilon))
