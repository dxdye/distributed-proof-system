"""Joint estimation of reviewer rates and item labels (Dawid & Skene 1979).

Binary variant for the review setting: every item is erroneous or correct;
every reviewer has a sensitivity ``s`` and a specificity ``c``. Without ground
truth, EM alternates between the posterior error probability of each item
(E-step) and the rates of each reviewer (M-step). Honeypots and refuted items
have *known* labels and fix the scale (concept §6.4), so the estimate cannot
drift into "everyone agrees, everyone is great".
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_EPS = 1e-4


@dataclass(frozen=True)
class Label:
    item: str
    reviewer: str
    incorrect: bool


@dataclass(frozen=True)
class DawidSkene:
    p_error: Mapping[str, float]  # posterior P(item erroneous)
    sensitivity: Mapping[str, float]
    specificity: Mapping[str, float]
    prior_error: float
    iterations: int


def _clip(p: float) -> float:
    return min(1 - _EPS, max(_EPS, p))


def dawid_skene(
    labels: Sequence[Label],
    known: Mapping[str, bool] | None = None,
    *,
    prior_error: float = 0.05,
    smoothing: float = 1.0,
    max_iter: int = 200,
    tol: float = 1e-7,
) -> DawidSkene:
    """EM estimate. ``known`` maps item → True if erroneous (honeypots, refutations)."""
    known = known or {}
    by_item: dict[str, list[Label]] = defaultdict(list)
    by_reviewer: dict[str, list[Label]] = defaultdict(list)
    for lab in labels:
        by_item[lab.item].append(lab)
        by_reviewer[lab.reviewer].append(lab)

    # Initialise with the share of "incorrect" votes (majority-like).
    p: dict[str, float] = {}
    for item, labs in by_item.items():
        if item in known:
            p[item] = 1.0 if known[item] else 0.0
        else:
            p[item] = sum(lab.incorrect for lab in labs) / len(labs)

    sens: dict[str, float] = {}
    spec: dict[str, float] = {}
    prior = prior_error
    iteration = 0
    for iteration in range(1, max_iter + 1):  # noqa: B007
        # M-step: rates with Beta(smoothing, smoothing) regularisation.
        for reviewer, labs in by_reviewer.items():
            err_mass = sum(p[lab.item] for lab in labs)
            ok_mass = len(labs) - err_mass
            hits = sum(p[lab.item] for lab in labs if lab.incorrect)
            confirms = sum(1 - p[lab.item] for lab in labs if not lab.incorrect)
            sens[reviewer] = _clip((hits + smoothing) / (err_mass + 2 * smoothing))
            spec[reviewer] = _clip((confirms + smoothing) / (ok_mass + 2 * smoothing))
        unknown = [i for i in by_item if i not in known]
        if unknown:
            prior = _clip((sum(p[i] for i in unknown) + smoothing) / (len(unknown) + 2 * smoothing))
        # E-step.
        delta = 0.0
        for item in unknown:
            x = math.log(prior / (1 - prior))
            for lab in by_item[item]:
                s, c = sens[lab.reviewer], spec[lab.reviewer]
                x += math.log(s / (1 - c)) if lab.incorrect else math.log((1 - s) / c)
            new = 1 / (1 + math.exp(-x)) if x > -700 else 0.0
            delta = max(delta, abs(new - p[item]))
            p[item] = new
        if delta < tol:
            break
    return DawidSkene(p, sens, spec, prior, iteration)
