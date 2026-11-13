"""Difficulty tiers of class-A tickets: easy, medium, hard, excellence.

The tier says how much a reviewer has to check, in absolute terms, so that a
short lemma about natural numbers is "easy" in every submission and a large
structure over Mathlib's analysis is "excellence" wherever it appears. (The
estimated difficulty b_i of concept §8.1 is standardised per submission. It
drives lease lengths, but is relative and hence unfit as a label.)

The score is computed from the ticket view, i.e. from what the reviewer sees:

* how much text there is (logarithmic);
* how many constants it uses, and how many of them come from libraries
  (Mathlib) or from the submission itself: each needs its definition checked
  or known;
* quantifier alternations (∀∃, ∃∀), the classic source of mistakes.

A honeypot carries the tier of its original. Thresholds are first guesses,
to be calibrated with the pilot's measured difficulty (concept §8.2, IRT).

Hard and excellence tickets are open to those who have earned it in the
ticket's domain: hard with the PV role, excellence with the PVV role
(concept §6.3), and to maintainers. Access, like weight, comes only from what
the log has measured; a self-declared group opens nothing, since a fake
account could otherwise occupy the scarce hard tickets. A ticket that has
waited longer than ``tier_gate_age_s`` is open to everyone, so that no class-A
ticket starves (SR-05).
"""

from __future__ import annotations

import math
from collections.abc import Collection
from itertools import pairwise
from typing import Literal

from dpc.tickets.views import UnitView

Tier = Literal["easy", "medium", "hard", "excellence"]
TIERS: tuple[Tier, ...] = ("easy", "medium", "hard", "excellence")

#: Upper bounds of the score for easy, medium and hard; above: excellence.
BOUNDS = (2.0, 4.5, 7.0)


def alternations(text: str) -> int:
    quantifiers = [c for c in text if c in "∀∃"]
    return sum(1 for a, b in pairwise(quantifiers) if a != b)


def score(view: UnitView) -> float:
    texts = [c.trusted_text or c.text for c in view.components]
    glossary = {g.name: g for c in view.components
                for g in (c.trusted_glossary or c.glossary)}
    library = sum(1 for g in glossary.values() if g.origin == "library")
    own = sum(1 for g in glossary.values() if g.origin == "submission")
    text = " ".join(texts)
    return (math.log2(1 + len(text) / 60) + 0.08 * len(glossary) + 0.25 * library
            + 0.4 * own + 0.6 * alternations(text))


def tier_of_score(value: float) -> Tier:
    for tier, bound in zip(TIERS, BOUNDS, strict=False):
        if value < bound:
            return tier
    return "excellence"


def tier_of_view(view: UnitView) -> Tier:
    return tier_of_score(score(view))


def tier_of(difficulty: float) -> Tier:
    """Fallback for tickets created before tiers were logged: the relative b_i."""
    for tier, bound in zip(TIERS, (-0.5, 0.5, 1.5), strict=False):
        if difficulty < bound:
            return tier
    return "excellence"


def tier_open(tier: Tier, *, roles: Collection[str], maintainer: bool) -> bool:
    """May someone with these roles (in the ticket's domain) take this tier?"""
    if tier in ("easy", "medium") or maintainer:
        return True
    if tier == "hard":
        return "PV" in roles
    return "PVV" in roles
