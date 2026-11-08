"""Simulation (M3): verification items of the SE document §11.2 for SR-11/12."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dpc.sim import ReviewerType, SimConfig, simulate

HONEST = ReviewerType("honest", 40)
CLICKER = ReviewerType("clicker", 6, behaviour="clicker")
LOOKUP = ReviewerType("lookup", 6, behaviour="lookup")


def test_simulation_is_deterministic() -> None:
    cfg = SimConfig(items=60, seed=7)
    assert simulate(cfg).as_dict() == simulate(cfg).as_dict()


@pytest.mark.req("SR-11")
def test_wrong_decisions_stay_rare_with_honest_reviewers() -> None:
    misses = errors = false_errors = items = 0
    for seed in range(3):
        result = simulate(SimConfig(items=300, reviewers=(HONEST,), seed=seed))
        misses += result.missed
        errors += result.erroneous
        false_errors += result.false_errors
        items += result.items
    assert errors > 20
    assert misses / errors < 0.05
    # False alarms only survive if the claim check errs (5 % in this model).
    assert false_errors / items < 0.02


@pytest.mark.req("SR-12")
def test_trust_estimates_converge() -> None:
    """Verification §11.2: convergence of the estimates for known s, c."""
    onboarding, after = [], []
    for seed in range(3):
        cfg = SimConfig(items=0, reviewers=(HONEST,), seed=seed)
        onboarding.append(simulate(cfg).by_kind["honest"]["mean_abs_error_s"])
        after.append(simulate(replace(cfg, items=400)).by_kind["honest"]["mean_abs_error_s"])
    assert sum(after) < sum(onboarding)
    assert sum(after) / len(after) < 0.11


@pytest.mark.req("SR-12")
def test_always_correct_clickers_never_review_class_a() -> None:
    result = simulate(SimConfig(items=200, reviewers=(HONEST, CLICKER), seed=1))
    assert result.by_kind["clicker"]["share_pv"] == 0.0
    assert result.by_kind["clicker"]["reviews"] == 0.0


@pytest.mark.req("SR-34")
def test_correlated_blind_spots_raise_the_miss_rate() -> None:
    base = SimConfig(items=400, error_rate=0.1, reviewers=(HONEST,), seed=2)
    independent = simulate(base)
    correlated = simulate(replace(base, blind_share=0.5))
    assert correlated.missed > independent.missed


def test_lookup_attack_inflates_trust_but_is_flagged() -> None:
    """Quantifies the risk recorded in docs/adr/0006 (assumption AS-5): gaming
    honeypots via the public repository yields *more* trust than honest work,
    and only the anomaly signal on confirmed real errors catches it."""
    result = simulate(SimConfig(items=500, error_rate=0.1, seed=3,
                                reviewers=(HONEST, CLICKER, LOOKUP)))
    lookup, honest = result.by_kind["lookup"], result.by_kind["honest"]
    assert lookup["mean_kappa"] > honest["mean_kappa"]
    assert lookup["reviews"] > 0
    assert lookup["flagged_suspicious"] >= 0.5
    assert honest["flagged_suspicious"] <= 0.05
