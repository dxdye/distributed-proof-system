"""Correlated errors and lenses (concept §8.3–8.4; SR-34).

Repetition alone saturates: with probability ``ρ`` an error is invisible to
everyone who uses the same approach, so ``P(miss) = ρ(1−q) + (1−ρ)(1−q)^k``
never drops below ``ρ(1−q)``. Lenses are review assignments focused on error
classes. The expected covered error mass

    Φ(L) = Σ_e f_e · (1 − Π_{ℓ∈L} (1 − d_{ℓ,e}))

is monotone and submodular, so greedy selection reaches at least ``1 − 1/e``
of the optimum (Nemhauser, Wolsey, Fisher 1978).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def miss_probability(q: float, k: int, rho: float) -> float:
    return rho * (1 - q) + (1 - rho) * (1 - q) ** k


def coverage(
    lenses: Sequence[Mapping[str, float]], frequencies: Mapping[str, float]
) -> float:
    total = 0.0
    for error_class, f in frequencies.items():
        missed = 1.0
        for lens in lenses:
            missed *= 1 - lens.get(error_class, 0.0)
        total += f * (1 - missed)
    return total


def greedy_lenses(
    candidates: Mapping[str, Mapping[str, float]],
    frequencies: Mapping[str, float],
    k: int,
    *,
    allow_repeat: bool = True,
) -> list[str]:
    """Pick ``k`` lenses greedily by marginal coverage gain."""
    chosen: list[str] = []
    for _ in range(k):
        current = coverage([candidates[c] for c in chosen], frequencies)
        best, gain = None, -1.0
        for name, lens in sorted(candidates.items()):
            if not allow_repeat and name in chosen:
                continue
            g = coverage([*(candidates[c] for c in chosen), lens], frequencies) - current
            if g > gain:
                best, gain = name, g
        if best is None:
            break
        chosen.append(best)
    return chosen
