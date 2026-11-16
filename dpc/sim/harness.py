"""The simulation against the real coordinator (review of 2026-11-16).

The parameter study (:mod:`dpc.sim.model`) models the process; the
coordinator implements it. The two drifted apart: the model draws only
people with the PV role for class A, the coordinator lets anyone fill the
k_min seats. This harness closes the gap for good: agents with the
behaviours of the model call the same :class:`~dpc.coord.Coordinator`
methods the API calls (choice sets, leases, reviews, PVV duties, claims,
escalations, reveals), with a fake clock and a fixed seed. The truth comes
from the real errors planted into the units and from the vault of planted
copies. Leases, tiers, choice sets, claims and the PVV bottleneck are thereby
simulated as they are built, and every later change to the coordinator is
measured with it.

Slow; the model stays for fast parameter grids.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from scipy.stats import beta as beta_dist

from dpc.audit import AuditLog
from dpc.coord import Conflict, CoordError, Coordinator, CoordParams, TicketSpec, Vault
from dpc.coord.state import TicketSt
from dpc.honeypots import HoneypotPool, MutantFileSource, Origin
from dpc.sim.model import Behaviour
from dpc.tickets.views import Component, UnitView

REASON = "the formal statement does not match the passage: a hypothesis is missing"
DOMAIN = "analysis"


@dataclass(frozen=True)
class AgentType:
    name: str
    count: int
    behaviour: Behaviour = "honest"
    s: tuple[float, float] = (8.0, 3.0)  # Beta parameters of the true sensitivity
    c: tuple[float, float] = (40.0, 1.5)  # … and specificity


@dataclass(frozen=True)
class HarnessConfig:
    units: int = 60
    error_rate: float = 0.05
    honeypot_share: float = 0.1
    agents: tuple[AgentType, ...] = (AgentType("honest", 12),
                                     AgentType("clicker", 3, behaviour="clicker"))
    #: Honest founding maintainers (C-42): the PVVs of the cold start.
    founding: int = 3
    days: int = 45
    target_share: float = 0.0  # share of real errors the attackers want to pass
    claim_accuracy: float = 0.95
    seed: int = 0
    params: CoordParams = field(default_factory=lambda: CoordParams(pair_window_s=0))


@dataclass
class Agent:
    rid: str
    behaviour: Behaviour
    s: float
    c: float
    founding: bool = False


@dataclass
class HarnessResult:
    real_units: int
    real_errors: int
    accepted: int
    accepted_wrong: int  # real errors that were accepted
    errors_found: int  # real errors decided as errors
    escalated: int
    open: int
    reviews: int
    #: accepted tickets whose deciding reviews included fewer than k_min by
    #: people who held the PV role when they reviewed (finding 1 of the review)
    filled_by_unqualified: int
    targets: int
    targets_passed: int
    by_behaviour: dict[str, int] = field(default_factory=dict)  # reviews per behaviour

    @property
    def miss_upper(self) -> float:
        """95 % Clopper-Pearson upper bound of the share of real errors accepted."""
        return clopper_pearson_upper(self.accepted_wrong, self.real_errors)

    def as_dict(self) -> dict[str, object]:
        return {**self.__dict__, "miss_upper": round(self.miss_upper, 3)}


def clopper_pearson_upper(k: int, n: int, conf: float = 0.95) -> float:
    """One-sided upper confidence bound of a binomial share: with 0 of 30 it
    is about 0.095 (the rule of three), not 0."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    return float(beta_dist.ppf(conf, k + 1, n - k))


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2027, 1, 4, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _view(name: str) -> UnitView:
    return UnitView(declaration=name, decl_kind="theorem",
                    components=(Component(target="type", text=f"statement of {name}"),))


class Harness:
    def __init__(self, cfg: HarnessConfig, work: Path) -> None:
        self.cfg, self.rng = cfg, np.random.default_rng(cfg.seed)
        self.clock = Clock()
        self.log = AuditLog(work / "log.sqlite", clock=self.clock)
        self.vault = Vault(work / "vault.sqlite")
        counter = iter(range(1, 10**9))
        params = replace(cfg.params, honeypot_share=cfg.honeypot_share)
        self.coord = Coordinator(self.log, self.vault, params, clock=self.clock,
                                 rng=np.random.default_rng(cfg.seed),
                                 new_id=lambda p: f"{p}-{next(counter):06d}")
        names = [f"H.u{i}" for i in range(cfg.units)]
        self.wrong = {n for n in names if self.rng.random() < cfg.error_rate}
        wrong_sorted = sorted(self.wrong)
        n_targets = round(cfg.target_share * len(wrong_sorted))
        self.targets = set(wrong_sorted[:n_targets])
        mutants = work / "mutants.jsonl"
        records = [{"kind": "header", "schema": "dpc.mutants/1", "toolchain": "x"}] + [
            {"kind": "mutant", "decl": n, "target": "type", "operator": "relation",
             "detail": "", "type_correct": True, "equivalent": False, "proof_script": None,
             "original": f"statement of {n}", "mutant": f"mutated {n}", "mutant_hash": n}
            for n in names]
        mutants.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
        pool = HoneypotPool([MutantFileSource(mutants, Origin.OWN_REPOSITORY)],
                            np.random.default_rng(cfg.seed))
        self.sid = self.coord.open_submission(
            title="Harness", repo_url="https://x/h", commit="c" * 40,
            tickets=[TicketSpec(_view(n), domain=DOMAIN) for n in names], pool=pool)
        admin = self.coord.register("harness-admin", notice_acknowledged=True)[0]
        self.coord.appoint_admin(admin)
        self.agents: list[Agent] = []
        for i in range(cfg.founding):
            rid = self.coord.register(f"founder{i}", "expert", notice_acknowledged=True)[0]
            self.coord.appoint_maintainer(admin, rid, [DOMAIN], reason="harness: founding",
                                          until=self.clock.now + timedelta(days=cfg.days + 30),
                                          founding=True)
            self.agents.append(Agent(rid, "honest", 0.9, 0.98, founding=True))
        for t in cfg.agents:
            for i in range(t.count):
                rid = self.coord.register(f"{t.name}{i}", notice_acknowledged=True)[0]
                self.agents.append(Agent(rid, t.behaviour, float(self.rng.beta(*t.s)),
                                         float(self.rng.beta(*t.c))))
        self.by_behaviour: Counter[str] = Counter()

    # ------------------------------------------------------------ truth
    def is_planted(self, ticket: TicketSt) -> bool:
        return self.vault.is_honeypot(ticket.ticket_id)

    def is_wrong(self, ticket: TicketSt) -> bool:
        return self.is_planted(ticket) or ticket.view.declaration in self.wrong

    def says_incorrect(self, agent: Agent, ticket: TicketSt) -> bool:
        """The verdicts of :meth:`dpc.sim.model.Simulation.verdict`."""
        planted = self.is_planted(ticket)
        if agent.behaviour == "clicker":
            return False
        if agent.behaviour == "lookup":
            return planted  # finds planted copies by comparison, misses real errors
        if agent.behaviour in ("sybil", "colluder"):
            if planted:
                return True
            if ticket.view.declaration in self.targets:
                return False
        if self.is_wrong(ticket):
            return bool(self.rng.random() < agent.s)
        return bool(self.rng.random() > agent.c)

    # ------------------------------------------------------------- steps
    def review(self, agent: Agent, lease_id: str, ticket: TicketSt) -> None:
        self.clock.now += timedelta(minutes=20)
        if self.says_incorrect(agent, ticket):
            self.coord.submit_review(agent.rid, lease_id, verdict="incorrect",
                                     failed=["fidelity"], reason=REASON)
        else:
            self.coord.submit_review(agent.rid, lease_id, verdict="correct")
        self.by_behaviour[agent.behaviour] += 1

    def take(self, agent: Agent) -> None:
        try:
            cs = self.coord.choice_set(agent.rid)
        except CoordError:
            return  # a limit on rerolling: try again tomorrow
        if cs is None or not cs.tickets:
            return
        choice = cs.tickets[0]
        if agent.behaviour in ("sybil", "colluder"):  # attackers take their targets
            for tid in cs.tickets:
                if self.coord.state.tickets[tid].view.declaration in self.targets:
                    choice = tid
                    break
        try:
            lease = self.coord.lease(agent.rid, cs.set_id, choice)
        except CoordError:
            return
        self.review(agent, lease.lease_id, self.coord.state.tickets[choice])

    def duties(self, agent: Agent) -> None:
        for _ in range(50):
            lease = self.coord.next_duty(agent.rid)
            if lease is None:
                return
            ticket = self.coord.state.tickets[lease.ticket_id]
            if lease.duty == "claim":
                truth = self.is_wrong(ticket)
                right = self.rng.random() < self.cfg.claim_accuracy
                self.clock.now += timedelta(minutes=10)
                self.coord.resolve_claim(agent.rid, lease.lease_id,
                                         confirmed=truth if right else not truth,
                                         reason="checked the finding against the passage")
            else:
                self.review(agent, lease.lease_id, ticket)

    def escalations(self) -> None:
        deciders = [a for a in self.agents if a.founding]
        for ticket in list(self.coord.state.tickets.values()):
            if ticket.status != "escalate":
                continue
            truth = self.is_wrong(ticket)
            right = self.rng.random() < self.cfg.claim_accuracy
            try:
                self.coord.maintainer_decide(deciders[0].rid, ticket.ticket_id,
                                             error=truth if right else not truth,
                                             reason="decided on the merits")
            except (Conflict, CoordError):
                continue

    def run(self) -> HarnessResult:
        for _ in range(self.cfg.days):
            order = self.rng.permutation(len(self.agents))
            for i in order:
                agent = self.agents[int(i)]
                self.take(agent)
                if agent.founding or "PVV" in self.coord.state.roles(
                        agent.rid, DOMAIN, self.clock.now):
                    self.duties(agent)
            self.escalations()
            self.clock.now += timedelta(days=1)
            self.coord.tick()
        return self.result()

    def result(self) -> HarnessResult:
        st, k_min = self.coord.state, self.coord.params.decision.k_min
        real = [t for t in st.tickets.values() if not self.is_planted(t)]
        accepted = [t for t in real if t.status == "accepted"]
        unqualified = sum(1 for t in accepted
                          if sum(1 for r in t.reviews if "PV" in r.roles) < k_min)
        return HarnessResult(
            real_units=len(real), real_errors=sum(1 for t in real if self.is_wrong(t)),
            accepted=len(accepted), accepted_wrong=sum(1 for t in accepted if self.is_wrong(t)),
            errors_found=sum(1 for t in real if t.status == "error" and self.is_wrong(t)),
            escalated=sum(1 for t in real if t.status == "escalate"),
            open=sum(1 for t in real if t.status == "open"),
            reviews=len(st.reviews), filled_by_unqualified=unqualified,
            targets=len(self.targets),
            targets_passed=sum(1 for t in accepted if t.view.declaration in self.targets),
            by_behaviour=dict(self.by_behaviour))

    def close(self) -> None:
        self.log.close()
        self.vault.close()


def run_harness(cfg: HarnessConfig) -> HarnessResult:
    with tempfile.TemporaryDirectory() as tmp:
        harness = Harness(cfg, Path(tmp))
        try:
            return harness.run()
        finally:
            harness.close()
