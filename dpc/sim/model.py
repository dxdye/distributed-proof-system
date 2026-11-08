"""Simulation model of class-A review.

Ground truth: each real item is erroneous with probability ``error_rate`` and
then belongs to an error class (concept §8.4). A share ``blind_share`` (ρ,
§8.3) of the errors is invisible to every reviewer with the usual approach;
only a lens focused on the error's class can find it. Honeypots carry a known,
visible error. Items and honeypots have a difficulty ``b``.

Detection models: ``beta`` — a reviewer finds a visible error with a fixed true
sensitivity; ``irt`` — with probability ``σ(a(θ − b))`` (concept §8.2), so
easy honeypots overstate how well hard real errors are found.

Reviewer behaviours:

* ``honest`` — as above; in Delphi round 2 switches to a shown justification
  with ``switch_true`` if it is right and ``switch_false`` if it is wrong,
* ``clicker`` — always "correct",
* ``lookup`` — recognises honeypots via the public repository, "correct"
  otherwise (docs/adr/0006),
* ``sybil`` — one attacker's accounts: gain trust via honeypot lookup, review
  competently, but always pass the attacker's *target* items (FMEA R6),
* ``colluder`` — like ``sybil``; in addition, as PVV of another colluder it
  confirms the PV's verdict unseen (collusion PV ↔ PVV).

Process per item (concept §4, §6, §8): reviewers with the PV role are drawn at
random (optionally each with a lens chosen greedily), a honeypot is mixed into
a reviewer's stream with probability ``h``; votes enter the decision rule with
the reviewers' *estimated* rates; optional Delphi round 2; a justified
"incorrect" opens a claim ticket that is checked directly; PVVs re-check at
rate ρ_u (no pair repetition within ``pair_window``, SR-08); after ``R``
rounds the item escalates to a maintainer. Confirmed errors are hard anchors.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np

from dpc.domain.anomaly import DetectionRecord, suspicious
from dpc.domain.decision import DecisionParams, Outcome, Vote, decide
from dpc.domain.lenses import greedy_lenses
from dpc.domain.review import detection_probability, recheck_probability
from dpc.domain.trust import RoleThresholds, Source, TrustState, record

Behaviour = Literal["honest", "clicker", "lookup", "sybil", "colluder"]
DetectionModel = Literal["beta", "irt"]

#: Error classes of concept §8.4 with provisional frequencies.
DEFAULT_ERROR_CLASSES: Mapping[str, float] = {
    "fidelity": 0.35, "junk_values": 0.2, "edge_cases": 0.2, "vacuity": 0.1, "quantifiers": 0.15,
}

#: Lenses of concept §8.4: probability that a lens finds a *blind* error of a class.
DEFAULT_LENSES: Mapping[str, Mapping[str, float]] = {
    "fidelity": {"fidelity": 0.6},
    "lean_semantics": {"junk_values": 0.6, "quantifiers": 0.5},
    "edge_cases": {"edge_cases": 0.6, "vacuity": 0.6},
    "devils_advocate": {c: 0.3 for c in DEFAULT_ERROR_CLASSES},
}


@dataclass(frozen=True)
class ReviewerType:
    name: str
    count: int
    behaviour: Behaviour = "honest"
    s: tuple[float, float] = (8.0, 3.0)  # Beta parameters of the true sensitivity (beta model)
    c: tuple[float, float] = (40.0, 1.5)  # … and specificity
    ability: tuple[float, float] = (1.0, 0.7)  # mean and sd of θ (IRT model)
    switch_true: float = 0.7  # Delphi: adopts a correct justification
    switch_false: float = 0.1  # Delphi: adopts a wrong justification


@dataclass(frozen=True)
class SimConfig:
    items: int = 300
    error_rate: float = 0.05
    blind_share: float = 0.0
    honeypot_share: float = 0.1
    onboarding_honeypots: int = 8
    onboarding_checked: int = 8  # real practice items checked by a maintainer (feeds c)
    claim_check_accuracy: float = 0.95  # checking a concrete claim is easy (§8.5)
    reviewers: tuple[ReviewerType, ...] = (
        ReviewerType("honest", 40),
        ReviewerType("clicker", 5, behaviour="clicker"),
    )
    decision: DecisionParams = field(default_factory=lambda: DecisionParams(
        prior_error=0.05, delta_a=1e-3, k_min=3, max_rounds=4))
    roles: RoleThresholds = field(default_factory=lambda: RoleThresholds(
        theta_pv=0.45, theta_pvv=0.7))
    detection_model: DetectionModel = "beta"
    discrimination: float = 1.5
    honeypot_difficulty_shift: float = 0.0  # < 0: honeypots easier than real errors
    error_classes: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_ERROR_CLASSES))
    lenses: bool = False
    lens_table: Mapping[str, Mapping[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_LENSES.items()})
    delphi: bool = False
    target_share: float = 0.0  # share of erroneous items an attacker wants accepted
    pair_window: int = 0  # SR-08: no (PV, PVV) pair repetition within the last n checks
    seed: int = 0


@dataclass(frozen=True)
class Item:
    error: bool
    blind: bool = False
    error_class: str | None = None
    difficulty: float = 0.0
    target: bool = False


@dataclass
class Reviewer:
    id: int
    kind: str
    behaviour: Behaviour
    true_s: float
    true_c: float
    ability: float = 0.0
    switch_true: float = 0.7
    switch_false: float = 0.1
    trust: TrustState = field(default_factory=TrustState)
    kappa: float = 0.0
    detections: DetectionRecord = field(default_factory=DetectionRecord)
    reviews: int = 0
    delphi: Counter[str] = field(default_factory=Counter)

    def update(self, said_incorrect: bool, source: Source, p_error: float = 1.0) -> None:
        self.trust = record(self.trust, said_incorrect, source, p_error=p_error)
        self.kappa = self.trust.kappa()


@dataclass(frozen=True)
class SimResult:
    items: int
    erroneous: int
    missed: int  # erroneous items accepted
    false_errors: int  # correct items declared erroneous
    escalated: int
    outcomes: dict[str, int]
    reviews: int
    honeypots_shown: int
    by_kind: dict[str, dict[str, float]]
    blind_errors: int = 0
    blind_missed: int = 0
    targets: int = 0
    targets_accepted: int = 0
    repeated_pairs: int = 0

    @property
    def miss_rate(self) -> float:
        return self.missed / self.erroneous if self.erroneous else 0.0

    @property
    def target_success(self) -> float:
        return self.targets_accepted / self.targets if self.targets else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "items": self.items, "erroneous": self.erroneous, "missed": self.missed,
            "miss_rate": round(self.miss_rate, 4), "false_errors": self.false_errors,
            "escalated": self.escalated, "outcomes": self.outcomes, "reviews": self.reviews,
            "reviews_per_item": round(self.reviews / max(1, self.items), 2),
            "honeypots_shown": self.honeypots_shown,
            "blind_errors": self.blind_errors, "blind_missed": self.blind_missed,
            "targets": self.targets, "targets_accepted": self.targets_accepted,
            "target_success": round(self.target_success, 4),
            "repeated_pairs": self.repeated_pairs, "by_kind": self.by_kind,
        }


class _Sim:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.reviewers: list[Reviewer] = []
        for t in cfg.reviewers:
            for _ in range(t.count):
                r = Reviewer(
                    len(self.reviewers), t.name, t.behaviour,
                    true_s=float(self.rng.beta(*t.s)), true_c=float(self.rng.beta(*t.c)),
                    ability=float(self.rng.normal(*t.ability)),
                    switch_true=t.switch_true, switch_false=t.switch_false,
                )
                r.kappa = r.trust.kappa()
                self.reviewers.append(r)
        self.honeypots_shown = 0
        self.reviews = 0
        self.classes = list(cfg.error_classes)
        weights = np.array([cfg.error_classes[c] for c in self.classes], dtype=float)
        self.class_p = weights / weights.sum()
        self.recent_pairs: deque[tuple[int, int]] = deque(maxlen=max(1, cfg.pair_window))
        self.pair_counts: Counter[tuple[int, int]] = Counter()
        self.repeated_pairs = 0

    # ------------------------------------------------------------ behaviour
    def detect(self, r: Reviewer, item: Item) -> float:
        """Probability of finding a visible error."""
        if self.cfg.detection_model == "irt":
            return detection_probability(r.ability, item.difficulty, self.cfg.discrimination)
        return r.true_s

    def verdict(self, r: Reviewer, item: Item, *, honeypot: bool = False,
                lens: str | None = None) -> bool:
        """True = "incorrect"."""
        if r.behaviour == "clicker":
            return False
        if r.behaviour == "lookup":
            return honeypot
        if r.behaviour in ("sybil", "colluder"):
            if honeypot:
                return True  # trust is farmed via repository lookup
            if item.target:
                return False  # the attacker's item must pass
        if item.error:
            if item.blind and not honeypot:
                hit = self.cfg.lens_table.get(lens or "", {}).get(item.error_class or "", 0.0)
                return bool(self.rng.random() < hit)
            return bool(self.rng.random() < self.detect(r, item))
        return bool(self.rng.random() > r.true_c)

    def honeypot(self, r: Reviewer) -> None:
        self.honeypots_shown += 1
        item = Item(error=True, difficulty=float(self.rng.normal())
                    + self.cfg.honeypot_difficulty_shift)
        found = self.verdict(r, item, honeypot=True)
        r.update(found, Source.HONEYPOT)
        d = r.detections
        r.detections = DetectionRecord(d.honeypots_seen + 1, d.honeypots_found + int(found),
                                       d.real_errors_seen, d.real_errors_found)

    def onboarding(self) -> None:
        for r in self.reviewers:
            for _ in range(self.cfg.onboarding_honeypots):
                self.honeypot(r)
            for _ in range(self.cfg.onboarding_checked):
                item = self.new_item(allow_target=False)
                said = self.verdict(r, item)
                r.update(said, Source.PVV, p_error=float(item.error))  # maintainer checks

    def new_item(self, *, allow_target: bool = True) -> Item:
        cfg = self.cfg
        error = bool(self.rng.random() < cfg.error_rate)
        if not error:
            return Item(False, difficulty=float(self.rng.normal()))
        return Item(
            error=True,
            blind=bool(self.rng.random() < cfg.blind_share),
            error_class=self.classes[int(self.rng.choice(len(self.classes), p=self.class_p))],
            difficulty=float(self.rng.normal()),
            target=allow_target and bool(self.rng.random() < cfg.target_share),
        )

    # -------------------------------------------------------------- process
    def draw(self, exclude: set[int], n: int, role: str) -> list[Reviewer]:
        th = self.cfg.roles.theta_pv if role == "PV" else self.cfg.roles.theta_pvv
        pool = [r for r in self.reviewers if r.id not in exclude and r.kappa >= th]
        if len(pool) < n:  # not enough qualified people: fall back to the most trusted
            rest = sorted((r for r in self.reviewers if r.id not in exclude and r not in pool),
                          key=lambda r: -r.kappa)
            pool += rest[: n - len(pool)]
        idx = self.rng.choice(len(pool), size=min(n, len(pool)), replace=False)
        return [pool[i] for i in idx]

    def pvv_check(self, pv: Reviewer, said: bool, item: Item, exclude: set[int]) -> None:
        if self.rng.random() >= recheck_probability(pv.kappa, incorrect=said, ticket_class="A"):
            return
        recent = {b for a, b in self.recent_pairs if a == pv.id} if self.cfg.pair_window else set()
        pvvs = self.draw(exclude | {pv.id} | recent, 1, "PVV")
        if pvvs and pvvs[0].kappa >= self.cfg.roles.theta_pvv:
            pvv = pvvs[0]
            pair = (pv.id, pvv.id)
            self.repeated_pairs += self.pair_counts[pair] > 0
            self.pair_counts[pair] += 1
            if self.cfg.pair_window:
                self.recent_pairs.append(pair)
            if pv.behaviour == "colluder" and pvv.behaviour == "colluder":
                pvv_says = said  # confirms the partner unseen
            else:
                pvv_says = self.verdict(pvv, item)
        else:  # nobody qualified: a maintainer decides
            pvv_says = item.error
        pv.update(said, Source.PVV, p_error=float(pvv_says))

    def lenses_for(self, k: int) -> list[str | None]:
        if not self.cfg.lenses:
            return [None] * k
        chosen = greedy_lenses(self.cfg.lens_table, self.cfg.error_classes, k)
        return list(chosen) + [None] * (k - len(chosen))

    def delphi_round(self, item: Item, voters: Sequence[tuple[Reviewer, bool]],
                     votes: list[Vote]) -> None:
        """Round 2: justifications become visible; switching is recorded as a
        signal, but round-2 votes are not independent (concept §8.6)."""
        if not any(v.incorrect and v.justified for v in votes):
            return
        claim_true = item.error  # a justification of "incorrect" is right iff there is an error
        for r, said in voters:
            if said or r.behaviour in ("clicker", "lookup") or item.target:
                continue
            key = "true" if claim_true else "false"
            r.delphi[f"seen_{key}"] += 1
            p = r.switch_true if claim_true else r.switch_false
            if self.rng.random() < p:
                r.delphi[f"switched_{key}"] += 1
                s_hat, c_hat = r.trust.point_estimates()
                votes.append(Vote(str(r.id), True, s_hat, c_hat, independent=False))

    def review_item(self, item: Item) -> Outcome:
        cfg, params = self.cfg, self.cfg.decision
        used: set[int] = set()
        votes: list[Vote] = []
        voters: list[tuple[Reviewer, bool]] = []
        rounds = 0
        while True:
            rounds += 1
            drawn = self.draw(used, params.k_min if rounds == 1 else 1, "PV")
            lenses = self.lenses_for(len(drawn)) if rounds == 1 else [None] * len(drawn)
            for r, lens in zip(drawn, lenses, strict=True):
                used.add(r.id)
                if self.rng.random() < cfg.honeypot_share:
                    self.honeypot(r)
                said = self.verdict(r, item, lens=lens)
                self.reviews += 1
                r.reviews += 1
                s_hat, c_hat = r.trust.point_estimates()
                votes.append(Vote(str(r.id), said, s_hat, c_hat, justified=said))
                voters.append((r, said))
                self.pvv_check(r, said, item, used)
            if cfg.delphi and rounds == 1:
                self.delphi_round(item, voters, votes)
            decision = decide(votes, params, pvv_reviewed=True, rounds=rounds)
            if decision.outcome is Outcome.CLAIM_PENDING:
                # A claim ticket checks the concrete justification directly.
                real = item.error
                confirmed = real if self.rng.random() < cfg.claim_check_accuracy else not real
                if confirmed:
                    outcome = Outcome.ERROR
                    break
                votes = [replace(v, justified=False) for v in votes]
                decision = decide(votes, params, pvv_reviewed=True, rounds=rounds)
            if decision.outcome in (Outcome.ACCEPTED, Outcome.ERROR, Outcome.ESCALATE):
                outcome = decision.outcome
                break
        if outcome is Outcome.ESCALATE:
            outcome = Outcome.ERROR if item.error else Outcome.ACCEPTED  # maintainer decides
        if outcome is Outcome.ERROR and item.error:
            for r, said in voters:  # confirmed error: hard anchor for every voter
                r.update(said, Source.REFUTATION)
                d = r.detections
                r.detections = DetectionRecord(d.honeypots_seen, d.honeypots_found,
                                               d.real_errors_seen + 1,
                                               d.real_errors_found + int(said))
        return outcome

    def run(self) -> SimResult:
        self.onboarding()
        counts: Counter[str] = Counter()
        erroneous = missed = false_errors = blind = blind_missed = targets = hits = 0
        for _ in range(self.cfg.items):
            item = self.new_item()
            outcome = self.review_item(item)
            counts[outcome.value] += 1
            accepted = outcome is Outcome.ACCEPTED
            erroneous += item.error
            missed += item.error and accepted
            false_errors += (not item.error) and outcome is Outcome.ERROR
            blind += item.blind
            blind_missed += item.blind and accepted
            targets += item.target
            hits += item.target and accepted
        return SimResult(
            items=self.cfg.items, erroneous=erroneous, missed=missed, false_errors=false_errors,
            escalated=counts.get("escalate", 0), outcomes=dict(counts), reviews=self.reviews,
            honeypots_shown=self.honeypots_shown, by_kind=self._by_kind(),
            blind_errors=blind, blind_missed=blind_missed, targets=targets,
            targets_accepted=hits, repeated_pairs=self.repeated_pairs,
        )

    def _by_kind(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for kind in sorted({r.kind for r in self.reviewers}):
            group = [r for r in self.reviewers if r.kind == kind]
            s_err = [abs(r.trust.s.mean - r.true_s) for r in group]
            delphi = sum((r.delphi for r in group), Counter())
            out[kind] = {
                "count": len(group),
                "mean_kappa": round(float(np.mean([r.kappa for r in group])), 3),
                "share_pv": round(sum(r.kappa >= self.cfg.roles.theta_pv for r in group)
                                  / len(group), 3),
                "mean_abs_error_s": round(float(np.mean(s_err)), 3),
                "flagged_suspicious": round(sum(suspicious(r.detections) for r in group)
                                            / len(group), 3),
                "reviews": float(sum(r.reviews for r in group)),
                "delphi_switch_true": _rate(delphi["switched_true"], delphi["seen_true"]),
                "delphi_switch_false": _rate(delphi["switched_false"], delphi["seen_false"]),
            }
        return out


def _rate(hits: int, seen: int) -> float:
    return round(hits / seen, 3) if seen else math.nan


def simulate(cfg: SimConfig) -> SimResult:
    """Run one simulation; deterministic for a given ``cfg.seed``."""
    return _Sim(cfg).run()


def sweep(base: SimConfig, seeds: Sequence[int]) -> list[SimResult]:
    """Replicate a configuration over several seeds."""
    return [simulate(replace(base, seed=s)) for s in seeds]
