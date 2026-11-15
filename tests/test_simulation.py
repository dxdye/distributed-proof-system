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


# ---------------------------------------------------------- extended model
def _runs(cfg: SimConfig, seeds: range = range(3)) -> list:  # type: ignore[type-arg]
    return [simulate(replace(cfg, seed=s)) for s in seeds]


def _share(hits: int, total: int) -> float:
    return hits / total if total else 0.0


@pytest.mark.slow
@pytest.mark.req("SR-34")
def test_lenses_find_blind_errors_that_repetition_misses() -> None:
    """Verification §11.2: lenses against identical reviews under correlated errors."""
    base = SimConfig(items=400, error_rate=0.1, blind_share=0.5, reviewers=(HONEST,))
    plain, lensed = _runs(base), _runs(replace(base, lenses=True))
    plain_rate = _share(sum(r.blind_missed for r in plain), sum(r.blind_errors for r in plain))
    lens_rate = _share(sum(r.blind_missed for r in lensed), sum(r.blind_errors for r in lensed))
    assert plain_rate > 0.95  # identical reviews never see a blind error
    assert lens_rate < 0.5


@pytest.mark.slow
def test_easy_honeypots_overstate_sensitivity() -> None:
    """Concept §8.2: honeypots must cover the whole difficulty range."""
    base = SimConfig(items=400, error_rate=0.1, reviewers=(HONEST,), detection_model="irt")
    matched, easy = _runs(base), _runs(replace(base, honeypot_difficulty_shift=-2.5))
    assert easy[0].by_kind["honest"]["mean_kappa"] > matched[0].by_kind["honest"]["mean_kappa"]
    assert (_share(sum(r.missed for r in easy), sum(r.erroneous for r in easy))
            > _share(sum(r.missed for r in matched), sum(r.erroneous for r in matched)))


@pytest.mark.slow
def test_delphi_switching_separates_judgement_from_influenceability() -> None:
    gullible = ReviewerType("gullible", 15, switch_false=0.6)
    result = _runs(SimConfig(items=400, error_rate=0.1, reviewers=(HONEST, gullible),
                             delphi=True))[0]
    honest, easily_led = result.by_kind["honest"], result.by_kind["gullible"]
    assert easily_led["delphi_switch_false"] > honest["delphi_switch_false"] + 0.3


@pytest.mark.slow
def test_sybil_attack_needs_a_majority_of_the_pool() -> None:
    """FMEA R6: random assignment plus the one-finding rule defeat a minority."""
    def success(sybils: int, honest: int) -> float:
        runs = _runs(SimConfig(items=400, error_rate=0.1, target_share=0.5, reviewers=(
            ReviewerType("honest", honest), ReviewerType("sybil", sybils, behaviour="sybil"))))
        return _share(sum(r.targets_accepted for r in runs), sum(r.targets for r in runs))

    assert success(5, 40) < 0.1
    assert success(40, 10) > 0.4


@pytest.mark.slow
@pytest.mark.req("SR-08")
def test_pair_window_prevents_repeated_pv_pvv_pairs() -> None:
    base = SimConfig(items=400, error_rate=0.1, target_share=0.5, reviewers=(
        ReviewerType("honest", 30), ReviewerType("colluder", 10, behaviour="colluder")))
    open_pairs = sum(r.repeated_pairs for r in _runs(base))
    windowed = sum(r.repeated_pairs for r in _runs(replace(base, pair_window=50)))
    assert windowed < 0.2 * open_pairs


@pytest.mark.req("SR-38", "SR-41")
def test_steering_helps_fake_accounts_and_identity_weight_stops_it() -> None:
    """C-32: an attacker who sees its targets more often (τ) passes more of
    them; shrinking the weight of weakly identified accounts stops that."""
    from dpc.domain.decision import DecisionParams
    from dpc.sim.model import ReviewerType, SimConfig, simulate

    def success(steer: float, weight: float = 1.0) -> float:
        cfg = SimConfig(items=300, error_rate=0.1, target_share=0.5,
                        reviewers=(ReviewerType("honest", 40),
                                   ReviewerType("sybil", 10, behaviour="sybil")),
                        decision=DecisionParams(prior_error=0.1, delta_a=1e-3, k_min=3,
                                                max_rounds=4),
                        steer=steer, weak_identity_weight=weight)
        runs = [simulate(replace(cfg, seed=s)) for s in (0, 1)]
        return sum(r.targets_accepted for r in runs) / sum(r.targets for r in runs)

    assert success(26.0) > success(1.0) + 0.3
    assert success(26.0, weight=0.5) < 0.15


def test_choosing_alone_is_a_lever() -> None:
    """τ = N·(1 − (1 − n/N)^m): one set per take gives τ = n."""
    from dpc.sim.study import steering_factor

    assert steering_factor(200, 4, 1) == pytest.approx(4.0)
    assert steering_factor(200, 4, 7) == pytest.approx(26.4, abs=0.1)
    assert steering_factor(200, 4, 25) > 75
