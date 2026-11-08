"""Decision on a class-A ticket (concept §6.4, §8.5; SR-11, SR-35).

Posterior odds that the declaration is erroneous, from the independent
verdicts of round 1 and the reviewers' point estimates ``ŝ``, ``ĉ``::

    log P(err)/P(ok) = log π₀/(1−π₀)
                     + Σ_j [ y_j log(ŝ_j/(1−ĉ_j)) + (1−y_j) log((1−ŝ_j)/ĉ_j) ]

with ``y_j = 1`` for "incorrect". Asymmetric aggregation (§8.5): a justified
"incorrect" opens a claim ticket and blocks acceptance until the claim is
decided — a single finding is never outvoted.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

_EPS = 1e-3


@dataclass(frozen=True)
class Vote:
    reviewer: str
    incorrect: bool
    s_hat: float
    c_hat: float
    justified: bool = False
    independent: bool = True  # round 1 only (Delphi, §8.6); one per chain (§9.4)


@dataclass(frozen=True)
class DecisionParams:
    prior_error: float = 0.02  # π₀
    delta_a: float = 1e-3  # δ_A
    k_min: int = 3
    max_rounds: int = 3  # R


class Outcome(Enum):
    ACCEPTED = "accepted"
    ERROR = "error"
    CLAIM_PENDING = "claim_pending"  # a justified finding awaits its claim ticket
    MORE_REVIEWS = "more_reviews"
    ESCALATE = "escalate"  # to maintainers


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    p_error: float
    independent_votes: int


def _clip(p: float) -> float:
    return min(1 - _EPS, max(_EPS, p))


def log_odds_error(votes: Sequence[Vote], prior_error: float) -> float:
    total = math.log(prior_error / (1 - prior_error))
    for v in votes:
        if not v.independent:
            continue
        s, c = _clip(v.s_hat), _clip(v.c_hat)
        total += math.log(s / (1 - c)) if v.incorrect else math.log((1 - s) / c)
    return total


def posterior_error(votes: Sequence[Vote], prior_error: float) -> float:
    x = log_odds_error(votes, prior_error)
    return 1 / (1 + math.exp(-x)) if x > -700 else 0.0


def decide(
    votes: Sequence[Vote],
    params: DecisionParams,
    *,
    pvv_reviewed: bool,
    refuted: bool = False,
    open_claims: int = 0,
    rounds: int = 1,
) -> Decision:
    """Apply the rule of concept §6.4 together with the one-finding rule."""
    independent = sum(1 for v in votes if v.independent)
    p = posterior_error(votes, params.prior_error)
    if refuted or p > 1 - params.delta_a:
        return Decision(Outcome.ERROR, 1.0 if refuted else p, independent)
    if open_claims > 0 or any(v.incorrect and v.justified for v in votes):
        return Decision(Outcome.CLAIM_PENDING, p, independent)
    if p < params.delta_a and independent >= params.k_min and pvv_reviewed:
        return Decision(Outcome.ACCEPTED, p, independent)
    if rounds >= params.max_rounds:
        return Decision(Outcome.ESCALATE, p, independent)
    return Decision(Outcome.MORE_REVIEWS, p, independent)
