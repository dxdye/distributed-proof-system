"""The simulation against the real coordinator (review of 2026-11-16)."""

from __future__ import annotations

from dataclasses import replace

from dpc.coord import CoordParams
from dpc.sim.harness import HarnessConfig, clopper_pearson_upper, run_harness

SMALL = HarnessConfig(units=30, error_rate=0.15, days=20, seed=1)


def test_only_qualified_votes_fill_k_min_in_the_real_coordinator() -> None:
    """Before 2026-11-16 fresh accounts filled k_min; the harness shows it,
    and shows that qualified seats end it."""
    before = run_harness(replace(SMALL, params=CoordParams(pair_window_s=0,
                                                           qualified_seats=False)))
    assert before.accepted > 0 and before.filled_by_unqualified > 0
    after = run_harness(SMALL)
    assert after.filled_by_unqualified == 0
    assert after.accepted_wrong == 0


def test_the_bounds_are_conservative() -> None:
    assert abs(clopper_pearson_upper(0, 30) - 0.0950) < 0.002  # the rule of three
    assert clopper_pearson_upper(0, 3000) < 0.001  # what confirming δ_A takes
    assert clopper_pearson_upper(3, 3) == 1.0
