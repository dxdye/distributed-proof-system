"""Domain core: trust model, decision rule, sampling, lenses, leases, maturity."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dpc.domain.anomaly import DetectionRecord, suspicious
from dpc.domain.attention import Choice, draw_choice_set, fit_plackett_luce
from dpc.domain.dawid_skene import Label, dawid_skene
from dpc.domain.decision import DecisionParams, Outcome, Vote, decide, posterior_error
from dpc.domain.forecast import completion_weeks, required_throughput
from dpc.domain.lease import Reliability, cycle_time, expected_delay, lease_duration
from dpc.domain.lenses import coverage, greedy_lenses, miss_probability
from dpc.domain.maturity import downgrade, effective_prl, priority, wsjf
from dpc.domain.review import detection_probability, recheck_probability
from dpc.domain.sampling import (
    certificate_bound,
    checks_needed,
    clopper_pearson,
    draw,
    draw_weights,
)
from dpc.domain.trust import (
    BetaRate,
    RoleThresholds,
    Source,
    TrustState,
    external_prior,
    record,
    time_factor,
)


# ------------------------------------------------------------- trust (SR-12)
@pytest.mark.req("SR-12")
def test_always_correct_has_high_accuracy_but_no_trust() -> None:
    state = TrustState()
    for _ in range(20):
        state = record(state, False, Source.HONEYPOT)  # misses every honeypot
    for _ in range(200):
        state = record(state, False, Source.CONSENSUS, p_error=0.0)  # agrees on correct items
    assert state.c.mean > 0.95
    assert state.kappa() < 0.01


@pytest.mark.req("SR-12")
def test_hard_anchors_outweigh_soft_agreement() -> None:
    hard = record(TrustState(), True, Source.HONEYPOT)
    soft = record(TrustState(), True, Source.CONSENSUS, p_error=1.0)
    assert hard.s.alpha - 1 == pytest.approx(1.0)
    assert soft.s.alpha - 1 == pytest.approx(0.2)


@pytest.mark.req("SR-12")
def test_decay_pulls_back_to_the_prior() -> None:
    rate = BetaRate(21.0, 3.0)
    decayed = rate.decay(lam=0.5, dt=1)
    assert (decayed.alpha, decayed.beta) == (11.0, 2.0)
    assert rate.decay(0.9, 0).alpha == rate.alpha
    assert rate.decay(0.9, 1000).alpha == pytest.approx(1.0)


@pytest.mark.req("SR-12")
def test_new_accounts_have_low_trust_even_after_a_few_hits() -> None:
    state = TrustState()
    for _ in range(3):
        state = record(state, True, Source.HONEYPOT)
        state = record(state, False, Source.PVV, p_error=0.0)
    assert state.s.mean > 0.75
    assert state.kappa() < 0.5
    assert RoleThresholds().roles(state) == frozenset()


@pytest.mark.req("SR-41")
def test_external_prior_is_capped() -> None:
    weak = external_prior({"mathoverflow": 10}, {"mathoverflow": 0.5})
    strong = external_prior({"mathoverflow": 10**9, "mathlib": 10**9},
                            {"mathoverflow": 1.0, "mathlib": 1.0}, a_max=5.0)
    assert 1.0 < weak.s.alpha < strong.s.alpha == 6.0
    assert strong.s.beta == 1.0


@pytest.mark.req("SR-29")
def test_time_factor() -> None:
    assert time_factor(30, 120) == 0.25
    assert time_factor(500, 120) == 1.0
    fast = record(TrustState(), True, Source.HONEYPOT, time_factor=0.25)
    assert fast.s.alpha == pytest.approx(1.25)


# ---------------------------------------------------------- decision (SR-11)
def _votes(n: int, incorrect: bool = False, s: float = 0.75, c: float = 0.95) -> list[Vote]:
    return [Vote(f"r{i}", incorrect, s, c) for i in range(n)]


@pytest.mark.req("SR-11")
def test_posterior_matches_closed_form() -> None:
    votes = _votes(3)
    expected_log_odds = math.log(0.05 / 0.95) + 3 * math.log(0.25 / 0.95)
    p = posterior_error(votes, 0.05)
    assert math.log(p / (1 - p)) == pytest.approx(expected_log_odds)


@pytest.mark.req("SR-11")
def test_acceptance_needs_k_min_votes_and_a_pvv() -> None:
    params = DecisionParams(prior_error=0.05, delta_a=1e-3, k_min=3)
    strong = _votes(4, s=0.9, c=0.99)
    assert decide(strong[:2], params, pvv_reviewed=True).outcome is Outcome.MORE_REVIEWS
    assert decide(strong, params, pvv_reviewed=False).outcome is Outcome.MORE_REVIEWS
    assert decide(strong, params, pvv_reviewed=True).outcome is Outcome.ACCEPTED


@pytest.mark.req("SR-11")
def test_escalation_after_max_rounds_and_refutation_decides() -> None:
    params = DecisionParams(k_min=3, max_rounds=2)
    weak = _votes(3, s=0.55, c=0.6)
    assert decide(weak, params, pvv_reviewed=True, rounds=2).outcome is Outcome.ESCALATE
    assert decide(weak, params, pvv_reviewed=True, refuted=True).outcome is Outcome.ERROR


@pytest.mark.req("SR-11")
def test_only_independent_votes_count() -> None:
    votes = [*_votes(3), Vote("chain", True, 0.99, 0.99, independent=False)]
    assert posterior_error(votes, 0.05) == posterior_error(_votes(3), 0.05)


@pytest.mark.req("SR-35")
def test_a_single_justified_finding_is_never_outvoted() -> None:
    params = DecisionParams(k_min=3)
    votes = [*_votes(9, s=0.95, c=0.99), Vote("lone", True, 0.3, 0.9, justified=True)]
    assert decide(votes, params, pvv_reviewed=True).outcome is Outcome.CLAIM_PENDING
    unjustified = [*votes[:-1], Vote("lone", True, 0.3, 0.9, justified=False)]
    assert decide(unjustified, params, pvv_reviewed=True).outcome is Outcome.ACCEPTED


# ------------------------------------------------------- PVV, IRT (SR-13, 33)
@pytest.mark.req("SR-13")
def test_recheck_rate() -> None:
    assert recheck_probability(0.0, incorrect=False, ticket_class="A") == pytest.approx(0.5)
    assert recheck_probability(1.0, incorrect=False, ticket_class="A") == pytest.approx(0.05)
    assert recheck_probability(1.0, incorrect=True, ticket_class="A") == 1.0
    assert recheck_probability(1.0, incorrect=True, ticket_class="B") == pytest.approx(0.05)


def test_irt_detection_probability() -> None:
    assert detection_probability(1.0, 1.0) == pytest.approx(0.5)
    assert detection_probability(2.0, 0.0) > detection_probability(0.0, 2.0)


# -------------------------------------------------------------- Dawid–Skene
def test_dawid_skene_recovers_rates_with_honeypots() -> None:
    rng = np.random.default_rng(1)
    reviewers = {f"r{i}": (rng.uniform(0.6, 0.95), rng.uniform(0.9, 0.99)) for i in range(25)}
    truth = {f"i{j}": bool(rng.random() < 0.1) for j in range(400)}
    known = {f"h{j}": True for j in range(60)}
    labels = []
    for item, err in {**truth, **known}.items():
        for r in rng.choice(list(reviewers), size=5, replace=False):
            s, c = reviewers[r]
            said = rng.random() < s if err else rng.random() > c
            labels.append(Label(item, str(r), bool(said)))
    result = dawid_skene(labels, known)
    accuracy = np.mean([(result.p_error[i] > 0.5) == e for i, e in truth.items()])
    s_err = np.mean([abs(result.sensitivity[r] - s) for r, (s, _) in reviewers.items()])
    assert accuracy > 0.97
    assert s_err < 0.12
    assert result.prior_error == pytest.approx(np.mean(list(truth.values())), abs=0.03)


# -------------------------------------------------- sampling (SR-14, SR-15)
@pytest.mark.req("SR-14")
def test_draw_weights_follow_reverse_degree_and_origin() -> None:
    pi = draw_weights({"a": 0, "b": 3, "c": 3}, origin={"c": 2.0})
    assert sum(pi.values()) == pytest.approx(1.0)
    assert pi["b"] == pytest.approx(4 * pi["a"])
    assert pi["c"] == pytest.approx(2 * pi["b"])
    sample = draw(pi, 20000, np.random.default_rng(0))
    assert sample.count("c") / len(sample) == pytest.approx(pi["c"], abs=0.02)


@pytest.mark.req("SR-15")
def test_certificate_example_from_the_concept() -> None:
    # q = 0.5, δ = 0.05, n = 6000  →  ε_w ≤ 0.1 %
    assert certificate_bound(6000, 0.5, 0.05) == pytest.approx(0.000998, abs=1e-6)
    assert checks_needed(0.003, 0.5) <= 2000  # ε_w ≲ 0.3 % needs a third (concept §9)
    lower, upper = clopper_pearson(25, 50)
    assert lower < 0.5 < upper
    assert clopper_pearson(0, 10)[0] == 0.0 and clopper_pearson(10, 10)[1] == 1.0


# ---------------------------------------------------------- lenses (SR-34)
@pytest.mark.req("SR-34")
def test_repetition_saturates_under_correlated_errors() -> None:
    # Table of concept §8.3 (q = 0.5, ρ = 0.3).
    assert miss_probability(0.5, 1, 0.3) == pytest.approx(0.50)
    assert miss_probability(0.5, 3, 0.3) == pytest.approx(0.24, abs=0.005)
    assert miss_probability(0.5, 10, 0.3) == pytest.approx(0.15, abs=0.005)


@pytest.mark.req("SR-34")
@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000))
def test_greedy_lenses_reach_the_submodular_guarantee(seed: int) -> None:
    rng = np.random.default_rng(seed)
    classes = [f"e{i}" for i in range(5)]
    freq = dict(zip(classes, rng.dirichlet(np.ones(5)), strict=True))
    lenses = {f"L{i}": {e: float(rng.uniform(0, 0.9)) for e in classes} for i in range(5)}
    k = 3
    chosen = greedy_lenses(lenses, freq, k, allow_repeat=False)
    best = max(coverage([lenses[n] for n in combo], freq)
               for combo in itertools.combinations(lenses, k))
    assert coverage([lenses[n] for n in chosen], freq) >= (1 - 1 / math.e) * best - 1e-12


# ------------------------------------------------- leases (SR-26, SR-27)
@pytest.mark.req("SR-26")
def test_lease_duration_and_delay() -> None:
    durations = list(range(1, 101))
    assert lease_duration(durations, alpha=0.1) == pytest.approx(90.1)
    assert expected_delay(0.3, 3.0) == pytest.approx(1.2857, abs=1e-3)
    assert cycle_time(10, 5) == 2


@pytest.mark.req("SR-27")
def test_lapsed_leases_only_affect_reliability() -> None:
    rel = Reliability()
    assert rel.wip_limit("A") == 1 or rel.wip_limit("A") == 2
    for _ in range(6):
        rel = rel.lapsed()
    assert rel.wip_limit("A") == 1 and rel.wip_limit("B") == 1
    for _ in range(30):
        rel = rel.completed()
    assert rel.wip_limit("A") == 2 and rel.wip_limit("B") == 5


# ---------------------------------------- maturity, priority (SR-40, 53, 58)
@pytest.mark.req("SR-40")
def test_effective_prl_across_repositories() -> None:
    # de Bruijn–Newman bound builds on QRH 7/8 (concept §10.1), in another repo.
    prl = {"repoA:QRH": 2, "repoB:deBruijnNewman": 4, "repoB:lemma": 5}
    deps = {"repoB:deBruijnNewman": ["repoA:QRH", "repoB:lemma"]}
    eff = effective_prl(prl, deps)
    assert eff == {"repoA:QRH": 2, "repoB:deBruijnNewman": 2, "repoB:lemma": 5}


@pytest.mark.req("SR-53")
def test_finding_downgrades_its_reach() -> None:
    prl = {"T": 4, "U": 3, "V": 0}
    assert downgrade(prl, ["T", "V"]) == {"T": 1, "U": 3, "V": 0}


@pytest.mark.req("SR-58")
def test_priority_ignores_size_and_wsjf_orders_work() -> None:
    sign_error = priority("K4", [(1.0, 3), (1.0, 3), (1.0, 3)])  # tiny diff, three results
    refactor = priority("K0", [(1.0, 5)] * 50)  # 5000 lines, cosmetic
    assert refactor == 0 < sign_error
    assert wsjf(10, urgency=2, effort=1) > wsjf(10, urgency=2, effort=5)


# ------------------------------------------------------ attention (SR-38/39)
@pytest.mark.req("SR-38")
def test_plackett_luce_recovers_known_interest() -> None:
    rng = np.random.default_rng(3)
    papers = [f"p{i}" for i in range(15)]
    true_psi = dict(zip(papers, rng.normal(0, 1, len(papers)), strict=True))
    choices = []
    for _ in range(3000):
        shown = list(rng.choice(papers, size=4, replace=False))
        w = np.exp([true_psi[p] for p in shown])
        chosen = shown[rng.choice(4, p=w / w.sum())]
        choices.append(Choice(tuple(str(s) for s in shown), str(chosen)))
    psi = fit_plackett_luce(choices)
    corr = np.corrcoef([true_psi[p] for p in papers], [psi[p] for p in papers])[0, 1]
    assert corr > 0.95


@pytest.mark.req("SR-39")
def test_choice_sets_prefer_open_class_a() -> None:
    rng = np.random.default_rng(0)
    sets = [draw_choice_set(["a1", "a2"], [f"b{i}" for i in range(50)], 4, rng)
            for _ in range(200)]
    assert all(len(s) == 4 and len(set(s)) == 4 for s in sets)
    assert np.mean([any(x.startswith("a") for x in s) for s in sets]) == 1.0


# ------------------------------------------------------- forecast (SR-42)
@pytest.mark.req("SR-42")
def test_forecast_quantiles() -> None:
    rng = np.random.default_rng(0)
    assert completion_weeks(850, [100, 100], rng) == {0.5: 9, 0.85: 9}
    q = completion_weeks(2000, [50, 150, 250, 100, 0], rng)
    assert q[0.5] <= q[0.85]
    assert required_throughput(2500, 10) == 250


# -------------------------------------------------------- anomaly (R1)
def test_lookup_gaming_is_flagged() -> None:
    gamer = DetectionRecord(honeypots_seen=40, honeypots_found=40,
                            real_errors_seen=15, real_errors_found=0)
    honest = DetectionRecord(40, 30, 15, 11)
    assert suspicious(gamer)
    assert not suspicious(honest)
    assert not suspicious(DetectionRecord(40, 40, 0, 0))  # no evidence yet
