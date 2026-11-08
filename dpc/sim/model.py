"""Simulation model of class-A review.

Ground truth: each real item is erroneous with probability ``error_rate``; a
share ``blind_share`` (ρ, concept §8.3) of the errors is invisible to every
reviewer with the usual approach. Honeypots carry a known, visible error.

Reviewer behaviours:

* ``honest`` — finds a visible error with its true sensitivity, confirms a
  correct item with its true specificity;
* ``clicker`` — always answers "correct" (FMEA: "immer korrekt klicken");
* ``lookup`` — recognises honeypots by comparing with the public repository
  and answers "correct" on everything else (docs/adr/0006).

Process per item (concept §4, §6, §8.5): reviewers with the PV role are drawn
at random, one honeypot is mixed into a reviewer's stream with probability
``h``; votes enter the decision rule with the reviewers' *estimated* rates; a
justified "incorrect" opens a claim ticket that is checked directly; PVVs re-
check verdicts at rate ρ_u (always for "incorrect"); after ``R`` rounds the
item escalates to a maintainer (oracle). Confirmed errors act as hard anchors.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from dpc.domain.anomaly import DetectionRecord, suspicious
from dpc.domain.decision import DecisionParams, Outcome, Vote, decide
from dpc.domain.review import recheck_probability
from dpc.domain.trust import RoleThresholds, Source, TrustState, record

Behaviour = Literal["honest", "clicker", "lookup"]


@dataclass(frozen=True)
class ReviewerType:
    name: str
    count: int
    behaviour: Behaviour = "honest"
    s: tuple[float, float] = (8.0, 3.0)  # Beta parameters of the *true* sensitivity
    c: tuple[float, float] = (40.0, 1.5)  # … and specificity


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
    seed: int = 0


@dataclass
class Reviewer:
    id: int
    kind: str
    behaviour: Behaviour
    true_s: float
    true_c: float
    trust: TrustState = field(default_factory=TrustState)
    kappa: float = 0.0
    detections: DetectionRecord = field(default_factory=DetectionRecord)
    reviews: int = 0

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

    @property
    def miss_rate(self) -> float:
        return self.missed / self.erroneous if self.erroneous else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "items": self.items, "erroneous": self.erroneous, "missed": self.missed,
            "miss_rate": round(self.miss_rate, 4), "false_errors": self.false_errors,
            "escalated": self.escalated, "outcomes": self.outcomes, "reviews": self.reviews,
            "reviews_per_item": round(self.reviews / max(1, self.items), 2),
            "honeypots_shown": self.honeypots_shown, "by_kind": self.by_kind,
        }


class _Sim:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.reviewers: list[Reviewer] = []
        for t in cfg.reviewers:
            for _ in range(t.count):
                s = float(self.rng.beta(*t.s))
                c = float(self.rng.beta(*t.c))
                r = Reviewer(len(self.reviewers), t.name, t.behaviour, s, c)
                r.kappa = r.trust.kappa()
                self.reviewers.append(r)
        self.honeypots_shown = 0
        self.reviews = 0

    # ------------------------------------------------------------ behaviour
    def verdict(self, r: Reviewer, error: bool, blind: bool, honeypot: bool) -> bool:
        """True = "incorrect"."""
        if r.behaviour == "clicker":
            return False
        if r.behaviour == "lookup":
            return honeypot
        if error:
            return (not blind) and self.rng.random() < r.true_s
        return bool(self.rng.random() > r.true_c)

    def honeypot(self, r: Reviewer) -> None:
        self.honeypots_shown += 1
        found = self.verdict(r, error=True, blind=False, honeypot=True)
        r.update(found, Source.HONEYPOT)
        d = r.detections
        r.detections = DetectionRecord(d.honeypots_seen + 1, d.honeypots_found + int(found),
                                       d.real_errors_seen, d.real_errors_found)

    def onboarding(self) -> None:
        for r in self.reviewers:
            for _ in range(self.cfg.onboarding_honeypots):
                self.honeypot(r)
            for _ in range(self.cfg.onboarding_checked):
                error = bool(self.rng.random() < self.cfg.error_rate)
                said = self.verdict(r, error, blind=False, honeypot=False)
                r.update(said, Source.PVV, p_error=float(error))  # maintainer as checker

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

    def pvv_check(self, pv: Reviewer, said: bool, error: bool, blind: bool,
                  exclude: set[int]) -> None:
        if self.rng.random() >= recheck_probability(pv.kappa, incorrect=said, ticket_class="A"):
            return
        pvvs = self.draw(exclude | {pv.id}, 1, "PVV")
        if pvvs and pvvs[0].kappa >= self.cfg.roles.theta_pvv:
            pvv_says = self.verdict(pvvs[0], error, blind, honeypot=False)
        else:  # nobody qualified: a maintainer decides
            pvv_says = error
        pv.update(said, Source.PVV, p_error=float(pvv_says))

    def review_item(self, error: bool, blind: bool) -> Outcome:
        cfg, params = self.cfg, self.cfg.decision
        used: set[int] = set()
        votes: list[Vote] = []
        voters: list[tuple[Reviewer, bool]] = []
        rounds = 0
        while True:
            rounds += 1
            for r in self.draw(used, params.k_min if rounds == 1 else 1, "PV"):
                used.add(r.id)
                if self.rng.random() < cfg.honeypot_share:
                    self.honeypot(r)
                said = self.verdict(r, error, blind, honeypot=False)
                self.reviews += 1
                r.reviews += 1
                s_hat, c_hat = r.trust.point_estimates()
                votes.append(Vote(str(r.id), said, s_hat, c_hat, justified=said))
                voters.append((r, said))
                self.pvv_check(r, said, error, blind, used)
            decision = decide(votes, params, pvv_reviewed=True, rounds=rounds)
            if decision.outcome is Outcome.CLAIM_PENDING:
                # A claim ticket checks the concrete justification directly.
                confirmed = error and not blind if self.rng.random() < cfg.claim_check_accuracy \
                    else not error
                if confirmed:
                    outcome = Outcome.ERROR
                    break
                votes = [Vote(v.reviewer, v.incorrect, v.s_hat, v.c_hat, justified=False)
                         for v in votes]
                decision = decide(votes, params, pvv_reviewed=True, rounds=rounds)
            if decision.outcome in (Outcome.ACCEPTED, Outcome.ERROR, Outcome.ESCALATE):
                outcome = decision.outcome
                break
        if outcome is Outcome.ESCALATE:
            outcome = Outcome.ERROR if error else Outcome.ACCEPTED  # maintainer decides
        if outcome is Outcome.ERROR and error:
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
        erroneous = missed = false_errors = 0
        for _ in range(self.cfg.items):
            error = bool(self.rng.random() < self.cfg.error_rate)
            blind = error and bool(self.rng.random() < self.cfg.blind_share)
            outcome = self.review_item(error, blind)
            counts[outcome.value] += 1
            erroneous += error
            missed += error and outcome is Outcome.ACCEPTED
            false_errors += (not error) and outcome is Outcome.ERROR
        return SimResult(
            items=self.cfg.items, erroneous=erroneous, missed=missed, false_errors=false_errors,
            escalated=counts.get("escalate", 0), outcomes=dict(counts), reviews=self.reviews,
            honeypots_shown=self.honeypots_shown, by_kind=self._by_kind(),
        )

    def _by_kind(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for kind in sorted({r.kind for r in self.reviewers}):
            group = [r for r in self.reviewers if r.kind == kind]
            s_err = [abs(r.trust.s.mean - r.true_s) for r in group]
            out[kind] = {
                "count": len(group),
                "mean_kappa": round(float(np.mean([r.kappa for r in group])), 3),
                "share_pv": round(sum(r.kappa >= self.cfg.roles.theta_pv for r in group)
                                  / len(group), 3),
                "mean_abs_error_s": round(float(np.mean(s_err)), 3),
                "flagged_suspicious": round(sum(suspicious(r.detections) for r in group)
                                            / len(group), 3),
                "reviews": float(sum(r.reviews for r in group)),
            }
        return out


def simulate(cfg: SimConfig) -> SimResult:
    """Run one simulation; deterministic for a given ``cfg.seed``."""
    return _Sim(cfg).run()


def sweep(base: SimConfig, seeds: Sequence[int]) -> list[SimResult]:
    """Replicate a configuration over several seeds."""
    from dataclasses import replace

    return [simulate(replace(base, seed=s)) for s in seeds]
