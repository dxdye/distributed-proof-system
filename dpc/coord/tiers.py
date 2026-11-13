"""Difficulty tiers of class-A tickets: easy, medium, hard, excellence.

The tier is a coarse reading of the estimated difficulty b_i (concept §8.1;
`dpc.tickets.difficulty`: standardised static features, about 0 on average).
It is shown on every ticket card and lets reviewers say what they want to
work on. A honeypot carries the difficulty of its original, hence its tier.

Hard and excellence tickets are open to those who can be expected to handle
them: through trust earned in the ticket's domain (PV, PVV), the declared
group, or the maintainer role. The declared group is self-reported, but it
only opens the door: the weight of a verdict always comes from measured
trust. A ticket that has waited longer than ``tier_gate_age_s`` is open to
everyone, so that no class-A ticket starves (SR-05).
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

Tier = Literal["easy", "medium", "hard", "excellence"]
TIERS: tuple[Tier, ...] = ("easy", "medium", "hard", "excellence")

#: Upper bounds of b_i for easy, medium and hard; above the last: excellence.
BOUNDS = (-0.5, 0.5, 1.5)


def tier_of(difficulty: float) -> Tier:
    for tier, bound in zip(TIERS, BOUNDS, strict=False):
        if difficulty < bound:
            return tier
    return "excellence"


def tier_open(tier: Tier, *, roles: Collection[str], group: str, maintainer: bool) -> bool:
    """May someone with these roles (in the ticket's domain) take this tier?"""
    if tier in ("easy", "medium") or maintainer:
        return True
    if tier == "hard":
        return "PV" in roles or group in ("expert", "doctoral")
    return "PVV" in roles or group == "expert"
