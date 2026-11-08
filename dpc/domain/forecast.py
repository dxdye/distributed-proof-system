"""Dates from forecasts (concept §11.3; SR-42).

Remaining work ``W`` in reviews, weekly throughput ``Λ_t`` bootstrapped from the
measured history: ``T = min{t : Σ_{t'≤t} Λ_t' ≥ W}``. Reported as quantiles; the
85 % value is the one communicated.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def completion_weeks(
    remaining: float,
    weekly_throughput: Sequence[float],
    rng: np.random.Generator,
    *,
    quantiles: Sequence[float] = (0.5, 0.85),
    runs: int = 10_000,
    max_weeks: int = 520,
) -> dict[float, int]:
    """Weeks until ``remaining`` reviews are done, per quantile."""
    history = np.asarray(weekly_throughput, dtype=float)
    if remaining <= 0:
        return dict.fromkeys(quantiles, 0)
    if history.size == 0 or history.max() <= 0:
        raise ValueError("no positive throughput observed yet")
    samples = rng.choice(history, size=(runs, max_weeks), replace=True)
    cumulative = samples.cumsum(axis=1)
    done = cumulative >= remaining
    weeks = np.where(done.any(axis=1), done.argmax(axis=1) + 1, max_weeks)
    return {q: int(np.ceil(np.quantile(weeks, q))) for q in quantiles}


def required_throughput(remaining: float, weeks_left: float) -> float:
    """Reverse question for external deadlines: reviews per week needed."""
    if weeks_left <= 0:
        raise ValueError("deadline already passed")
    return remaining / weeks_left
