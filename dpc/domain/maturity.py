"""Proof readiness levels and the priority of findings
(concept §10.1, §13.4–13.5; SR-40, SR-53, SR-58).

``PRL_eff(T) = min(PRL(T), min_{d ∈ deps(T)} PRL_eff(d))`` — a result is at
most as well secured as the weakest result it builds on, across repository
boundaries. A confirmed finding at ``d`` provisionally caps everything in its
reach ``R(d)`` at PRL 1 ("disputed").

Priority of a finding: ``Prio(f) = σ(K) · Σ_{T ∈ R(d)} γ(T)(1 + PRL(T))``.
Lines of code are deliberately absent; they only enter the effort ``E(f)`` of
``WSJF = Prio · U / E``, which orders repair work.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

PRL_MIN, PRL_MAX = 0, 5
DISPUTED = 1

#: Severity weights of the outcome classes K0–K4 (provisional, concept §13.4).
SEVERITY: Mapping[str, float] = {"K0": 0.0, "K1": 1.0, "K2": 3.0, "K3": 10.0, "K4": 30.0}


def effective_prl(
    prl: Mapping[str, int], deps: Mapping[str, Iterable[str]]
) -> dict[str, int]:
    """Fixpoint of the min-propagation; unknown dependencies count as PRL 0."""
    eff = {node: prl[node] for node in prl}
    changed = True
    while changed:
        changed = False
        for node in prl:
            lowest = min((eff.get(d, PRL_MIN) for d in deps.get(node, ())), default=PRL_MAX)
            value = min(prl[node], lowest)
            if value < eff[node]:
                eff[node] = value
                changed = True
    return eff


def downgrade(prl: Mapping[str, int], reach: Iterable[str]) -> dict[str, int]:
    """Cap every result in ``R(d)`` at PRL 1 after a confirmed finding (SR-53)."""
    affected = set(reach)
    return {node: min(level, DISPUTED) if node in affected else level
            for node, level in prl.items()}


def priority(outcome_class: str, affected: Iterable[tuple[float, int]]) -> float:
    """``affected``: ``(γ(T), PRL(T))`` for every ``T ∈ R(d)``; γ = 1 for a main
    theorem, about 0.1 for TCB lemmas. Until the outcome is known, use K3."""
    sigma = SEVERITY[outcome_class]
    return sigma * sum(gamma * (1 + level) for gamma, level in affected)


def wsjf(prio: float, urgency: float, effort: float) -> float:
    """Weighted shortest job first; LOC belong into ``effort`` only."""
    if effort <= 0:
        raise ValueError("effort must be positive")
    return prio * urgency / effort
