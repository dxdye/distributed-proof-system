"""Attention from choice decisions (concept §10.2; SR-38, SR-39).

Reviewers get a small random choice set and must work on what they pick, so a
choice is not a free click. Under Plackett–Luce / multinomial logit,
``P(j | S) = exp(ψ_j) / Σ_{k∈S} exp(ψ_k)``. ψ is estimated per group (experts,
doctoral students, students) with choices weighted by trust; the MM algorithm
of Hunter (2004) is used.

Attention orders papers; it never decides whether class A is reviewed
(SR-39) — choice sets are drawn so that open class-A tickets are preferred.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Choice:
    shown: tuple[str, ...]
    chosen: str
    weight: float = 1.0  # e.g. trust of the chooser; only choices with finished work count


def fit_plackett_luce(
    choices: Sequence[Choice], *, max_iter: int = 1000, tol: float = 1e-9, prior: float = 0.5
) -> dict[str, float]:
    """Interest values ψ (log-strengths, mean 0). ``prior`` adds a pseudo-win
    against a virtual neutral item so that never-chosen items stay finite."""
    items = sorted({i for ch in choices for i in ch.shown})
    if not items:
        return {}
    strength = dict.fromkeys(items, 1.0)
    wins: dict[str, float] = defaultdict(float)
    for ch in choices:
        if ch.chosen not in ch.shown:
            raise ValueError("the chosen item must be part of the choice set")
        wins[ch.chosen] += ch.weight
    for _ in range(max_iter):
        denom: dict[str, float] = defaultdict(float)
        for ch in choices:
            total = sum(strength[i] for i in ch.shown)
            for i in ch.shown:
                denom[i] += ch.weight / total
        new = {}
        for i in items:
            # Pseudo-observation: one comparison against a neutral item of strength 1.
            numerator = wins[i] + prior
            denominator = denom[i] + 2 * prior / (strength[i] + 1.0)
            new[i] = numerator / denominator
        delta = max(abs(math.log(new[i] / strength[i])) for i in items)
        strength = new
        if delta < tol:
            break
    logs = {i: math.log(strength[i]) for i in items}
    mean = sum(logs.values()) / len(logs)
    return {i: v - mean for i, v in logs.items()}


def draw_choice_set(
    open_class_a: Sequence[str], others: Sequence[str], size: int, rng: np.random.Generator,
    *, class_a_share: float = 0.5,
) -> list[str]:
    """Random choice set in random order; open class-A tickets are preferred
    so that attention cannot starve class A (SR-39)."""
    n_a = min(len(open_class_a), max(1, round(size * class_a_share))) if open_class_a else 0
    picked = list(rng.choice(open_class_a, size=n_a, replace=False)) if n_a else []
    rest = [o for o in others if o not in picked]
    n_rest = min(len(rest), size - len(picked))
    if n_rest:
        picked += list(rng.choice(rest, size=n_rest, replace=False))
    order = rng.permutation(len(picked))
    return [str(picked[i]) for i in order]


def choice_probabilities(psi: Mapping[str, float], shown: Sequence[str]) -> dict[str, float]:
    weights = {i: math.exp(psi.get(i, 0.0)) for i in shown}
    total = sum(weights.values())
    return {i: w / total for i, w in weights.items()}
