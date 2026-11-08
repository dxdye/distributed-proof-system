"""Leases, reliability and WIP limits (concept §9.1, §11.5; SR-26, SR-27).

A ticket is lent, not owned. The lease duration is the ``(1 − α)``-quantile of
the processing times of finished tickets of the same class and difficulty, so
only ``α`` of honest workers are cut off. Letting a lease lapse says nothing
about competence: it only affects a separate reliability ``r_u``, which sets
the work-in-progress limit — never ``s``, ``c`` or ``κ``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from dpc.domain.trust import BetaRate


def lease_duration(durations: Sequence[float], alpha: float = 0.1) -> float:
    """``τ = F⁻¹(1 − α)`` of observed processing times."""
    if not durations:
        raise ValueError("no finished tickets to derive a lease duration from")
    return float(np.quantile(np.asarray(durations, dtype=float), 1 - alpha))


def expected_delay(abort_rate: float, tau: float) -> float:
    """Mean delay per ticket ``a/(1−a)·τ`` for abort rate ``a`` (e.g. 0.3, 3 d → 1.3 d)."""
    if not 0 <= abort_rate < 1:
        raise ValueError("abort rate must be in [0, 1)")
    return abort_rate / (1 - abort_rate) * tau


@dataclass(frozen=True)
class Reliability:
    """Completion record. Active returns are free and therefore not recorded."""

    # Benefit of the doubt for newcomers.
    rate: BetaRate = field(default_factory=lambda: BetaRate(2.0, 1.0))

    def completed(self) -> Reliability:
        return Reliability(self.rate.update(success=True))

    def lapsed(self) -> Reliability:
        return Reliability(self.rate.update(success=False))

    def wip_limit(self, ticket_class: str) -> int:
        """Concurrent leases allowed (e.g. up to 2 in class A, 5 in class B)."""
        top = 2 if ticket_class == "A" else 5
        r = self.rate.mean
        if r >= 0.8:
            return top
        if r >= 0.5:
            return max(1, top - 1)
        return 1


def cycle_time(work_in_progress: float, throughput: float) -> float:
    """Little's law: cycle time = WIP / throughput (concept §11.5)."""
    if throughput <= 0:
        raise ValueError("throughput must be positive")
    return work_in_progress / throughput
