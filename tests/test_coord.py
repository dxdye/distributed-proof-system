"""Coordination service (M4): leases, choice sets, exclusion, claims, decisions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from dpc.audit import AuditLog
from dpc.coord import (
    BlobStore,
    Conflict,
    CoordError,
    Coordinator,
    CoordParams,
    Forbidden,
    TicketSpec,
    Vault,
    commitment,
)
from dpc.coord.tiers import tier_of, tier_of_view, tier_open
from dpc.domain.decision import DecisionParams
from dpc.domain.trust import Source
from dpc.honeypots import HoneypotPool, Mutant, MutantFileSource, Origin
from dpc.tickets.views import Component, GlossaryEntry, UnitView

LAB = "Frontier Lab"


@dataclass
class Clock:
    now: datetime = field(default_factory=lambda: datetime(2026, 11, 9, 8, 0, tzinfo=UTC))

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


def view(name: str) -> UnitView:
    return UnitView(declaration=name, decl_kind="theorem",
                    components=(Component(target="type", text=f"statement of {name}"),))


def specs(prefix: str, n: int) -> list[TicketSpec]:
    return [TicketSpec(view(f"{prefix}.u{i}"), domain="analysis") for i in range(n)]


class Env:
    """A coordinator on a fresh log with a fake clock."""

    def __init__(self, tmp: Path, params: CoordParams, seed: int = 0) -> None:
        self.tmp, self.params, self.clock = tmp, params, Clock()
        self.log = AuditLog(tmp / "log.sqlite", clock=self.clock)
        self.vault = Vault(tmp / "vault.sqlite")
        self.counter = 0
        self.coord = self.make(seed)

    def make(self, seed: int = 0) -> Coordinator:
        return Coordinator(self.log, self.vault, self.params, blobs=BlobStore(self.tmp / "blobs"),
                           clock=self.clock, rng=np.random.default_rng(seed), new_id=self.new_id)

    def new_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter:06d}"

    def people(self, n: int, prefix: str = "rev", **kw: object) -> list[str]:
        return [self.coord.register(f"{prefix}{i}", notice_acknowledged=True, **kw)[0]
                for i in range(n)]  # type: ignore[arg-type]

    def take(self, rid: str, ticket_id: str | None = None) -> str:
        """Lease ``ticket_id`` (or any ticket) via a choice set."""
        cs = self.coord.choice_set(rid)
        assert cs is not None, "nothing to do"
        if ticket_id is None:
            ticket_id = cs.tickets[0]
        assert ticket_id in cs.tickets
        return self.coord.lease(rid, cs.set_id, ticket_id).lease_id

    def events(self, kind: str) -> list[dict[str, object]]:
        return [e.payload for e in self.log.entries() if e.kind == kind]


def params(**kw: object) -> CoordParams:
    base = CoordParams(pair_window_s=0, honeypot_share=0.0, t_min_s=60.0,
                       decision=DecisionParams(prior_error=0.02, delta_a=1e-3, k_min=3,
                                               max_rounds=3))
    return replace(base, **kw)  # type: ignore[arg-type]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


# ------------------------------------------------------------ registration
@pytest.mark.req("SR-23", "SR-49")
def test_registration_is_pseudonymous_and_discloses_data_use(env: Env) -> None:
    with pytest.raises(Forbidden, match="SR-49"):
        env.coord.register("alice", notice_acknowledged=False)
    rid, token = env.coord.register("alice", "doctoral", [LAB], notice_acknowledged=True)
    assert env.vault.reviewer_for_token(token) == rid and env.vault.pseudonym(rid) == "alice"
    with pytest.raises(Conflict):
        env.coord.register("alice", notice_acknowledged=True)
    log_text = json.dumps([e.payload for e in env.log.entries()])
    assert "alice" not in log_text and "Frontier" not in log_text  # ids and keyed hashes only
    tags = env.events("reviewer.registered")[0]["affiliation_tags"]
    assert tags == [env.vault.tag(" frontier  LAB")]  # normalised before hashing


# ---------------------------------------------------------------- tickets
@pytest.mark.req("SR-05", "SR-06")
def test_every_unit_gets_a_ticket_and_honeypot_status_is_only_committed(tmp_path: Path) -> None:
    env = Env(tmp_path, params(honeypot_share=0.2))
    mutants = tmp_path / "mutants.jsonl"
    records = [{"kind": "header", "schema": "dpc.mutants/1", "toolchain": "x"}] + [
        {"kind": "mutant", "decl": f"P.u{i}", "target": "type", "operator": "relation",
         "detail": "", "type_correct": True, "equivalent": False, "proof_script": None,
         "original": f"statement of P.u{i}", "mutant": f"mutated P.u{i}", "mutant_hash": str(i)}
        for i in range(8)]
    mutants.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    pool = HoneypotPool([MutantFileSource(mutants, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(0))
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 16), pool=pool)
    created = env.events("ticket.created")
    assert len(created) == 20  # 16 units + 4 honeypots = 20 %
    assert {c["view"]["declaration"] for c in created} == {f"P.u{i}" for i in range(16)}
    assert "honeypot" not in json.dumps(created) and "mutated" in json.dumps(created)
    # Closing opens every commitment; anyone can check them against the log.
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    env.coord.close_submission(admin, sid)
    (reveal,) = env.events("honeypots.revealed")
    assert reveal["final"] and len(reveal["openings"]) == 20  # type: ignore[arg-type]
    from dpc.coord.events import Opening
    by_ticket = {c["ticket_id"]: c["commitment"] for c in created}
    openings = [Opening.model_validate(o) for o in reveal["openings"]]  # type: ignore[union-attr]
    assert all(commitment(o) == by_ticket[o.ticket_id] for o in openings)
    assert sum(o.honeypot for o in openings) == 4


# ------------------------------------------------------------- choice sets
@pytest.mark.req("SR-38")
def test_choice_sets_come_from_different_papers_and_the_choice_is_binding(env: Env) -> None:
    for paper in "PQRS":
        env.coord.open_submission(title=paper, repo_url="https://x", commit="c" * 40,
                                  tickets=specs(paper, 3))
    (rid,) = env.people(1)
    cs = env.coord.choice_set(rid)
    assert cs is not None and len(cs.tickets) == 4
    papers = {env.coord.state.tickets[t].submission_id for t in cs.tickets}
    assert len(papers) == 4  # one ticket per paper while there are enough papers
    assert env.coord.choice_set(rid) is cs  # no rerolling while the set is open
    other = next(t for t in env.coord.state.tickets if t not in cs.tickets)
    with pytest.raises(CoordError, match="not in the choice set"):
        env.coord.lease(rid, cs.set_id, other)
    env.coord.lease(rid, cs.set_id, cs.tickets[2])
    with pytest.raises(Conflict, match="used up"):
        env.coord.lease(rid, cs.set_id, cs.tickets[1])


@pytest.mark.req("SR-39")
def test_choice_sets_cover_all_open_class_a_tickets(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 12))
    seen: set[str] = set()
    for rid in env.people(30):
        cs = env.coord.choice_set(rid)
        assert cs is not None
        seen |= set(cs.tickets)
    assert seen == set(env.coord.state.tickets)  # attention cannot starve a ticket


# --------------------------------------------------------------- exclusion
@pytest.mark.req("SR-08", "SR-50")
def test_authors_affiliated_people_and_repeated_pairs_are_excluded(tmp_path: Path) -> None:
    env = Env(tmp_path, params(pair_window_s=7 * 86400))
    author, insider, a, b, c = (env.coord.register(n, notice_acknowledged=True)[0]
                                for n in ("author", "insider", "ann", "bob", "cyd"))
    env.coord.declare_affiliation(insider, "frontier lab")
    sid = env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                                    tickets=specs("P", 3), lab=LAB, authors=[author])
    t1, t2, _ = env.coord.state.submissions[sid].tickets
    ticket = env.coord.state.tickets[t1]
    assert "SR-08" in str(env.coord.why_not(author, ticket, "review"))
    assert "SR-50" in str(env.coord.why_not(insider, ticket, "review"))
    assert env.coord.choice_set(insider) is None
    la, lb = env.take(a, t1), env.take(b, t1)
    assert "already involved" in str(env.coord.why_not(a, ticket, "review"))
    env.clock.advance(hours=1)
    env.coord.submit_review(a, la, verdict="correct")
    env.coord.submit_review(b, lb, verdict="correct")
    # a and b reviewed together: not again within Δ_pair; c may join either.
    env.take(a, t2)
    assert "Δ_pair" in str(env.coord.why_not(b, env.coord.state.tickets[t2], "review"))
    assert env.coord.why_not(c, env.coord.state.tickets[t2], "review") is None
    env.clock.advance(days=8)
    assert env.coord.why_not(b, env.coord.state.tickets[t2], "review") is None


@pytest.mark.req("SR-28")
def test_class_a_is_issued_to_k_min_plus_one_in_parallel(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 1))
    (tid,) = env.coord.state.tickets
    people = env.people(5)
    for rid in people[:4]:
        env.take(rid, tid)
    assert env.coord.why_not(people[4], env.coord.state.tickets[tid], "review") == \
        "no free review slot"


# ------------------------------------------------------------------ leases
@pytest.mark.req("SR-26", "SR-27", "SR-30")
def test_leases_extend_once_return_freely_and_lapses_touch_reliability_only(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 4))
    (rid,) = env.people(1)
    lease_id = env.take(rid)
    lease = env.coord.state.leases[lease_id]
    assert lease.expires - lease.granted == timedelta(seconds=env.params.default_lease_s)
    assert 0 < lease.expected_s < env.params.default_lease_s  # shown instead of a countdown
    first = lease.expires
    env.coord.extend(rid, lease_id)
    assert env.coord.state.leases[lease_id].expires > first
    with pytest.raises(Conflict, match="once"):
        env.coord.extend(rid, lease_id)
    reliability = env.coord.state.reviewers[rid].reliability
    env.coord.return_lease(rid, lease_id)
    assert env.coord.state.reviewers[rid].reliability == reliability  # no penalty
    trust_before = env.coord.state.trust(rid, "analysis", env.clock())
    env.take(rid)
    env.clock.advance(days=30)
    assert env.coord.tick()["expired"] == 1
    person = env.coord.state.reviewers[rid]
    assert person.reliability.rate.mean < reliability.rate.mean
    assert env.coord.state.trust(rid, "analysis", env.clock()) == \
        trust_before.decay(env.params.decay_per_day, 30)  # only decay, no evidence


@pytest.mark.req("SR-26")
def test_lease_duration_follows_observed_processing_times(tmp_path: Path) -> None:
    env = Env(tmp_path, params(lease_min_samples=5))
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 10))
    people = env.people(8)
    for i, rid in enumerate(people[:5]):
        lease_id = env.take(rid)
        env.clock.advance(hours=2 + i)
        env.coord.submit_review(rid, lease_id, verdict="correct")
    ticket = next(iter(env.coord.state.tickets.values()))
    tau, expected = env.coord.lease_duration("review", ticket)
    assert tau == int(5.6 * 3600) and expected == 4 * 3600  # 90 % quantile, median
    lease = env.coord.state.leases[env.take(people[5])]
    assert lease.expires - lease.granted == timedelta(seconds=tau)


# ----------------------------------------------------------------- reviews
@pytest.mark.req("SR-09", "SR-29", "SR-35")
def test_incorrect_needs_a_reason_and_opens_a_claim_that_blocks_acceptance(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 1))
    (tid,) = env.coord.state.tickets
    people = env.people(4)
    leases = [env.take(rid, tid) for rid in people]
    with pytest.raises(CoordError, match="SR-09"):
        env.coord.submit_review(people[0], leases[0], verdict="incorrect")
    with pytest.raises(CoordError, match="question that fails"):
        env.coord.submit_review(people[0], leases[0], verdict="incorrect",
                                reason="n = 0 makes the hypothesis vacuous")
    with pytest.raises(CoordError, match="at least 30 characters"):
        env.coord.submit_review(people[0], leases[0], verdict="incorrect", reason="idk",
                                failed=["vacuity"])
    env.clock.advance(seconds=30)  # faster than t_min: down-weighted, not refused (SR-29)
    env.coord.submit_review(people[0], leases[0], verdict="incorrect",
                            reason="n = 0 makes the hypothesis vacuous", failed=["vacuity"],
                            evidence=b"example : False := by sorry", evidence_kind="vacuity")
    review = env.events("review.submitted")[0]
    assert float(review["t_factor"]) == pytest.approx(0.5)  # type: ignore[arg-type]
    assert review["evidence"]["file_sha256"] == env.coord.blobs.put(  # type: ignore[index, union-attr]
        b"example : False := by sorry")
    assert len(env.events("claim.opened")) == 1
    env.clock.advance(hours=1)
    for rid, lease_id in zip(people[1:], leases[1:], strict=True):
        env.coord.submit_review(rid, lease_id, verdict="correct")
    assert env.coord.state.tickets[tid].status == "open"  # one finding is never outvoted
    assert not env.events("ticket.decided")


@pytest.mark.req("SR-11", "SR-13", "SR-35")
def test_confirmed_claim_decides_error_and_anchors_every_verdict(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 1))
    (tid,) = env.coord.state.tickets
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    people = env.people(4)
    leases = [env.take(rid, tid) for rid in people]
    env.clock.advance(hours=1)
    env.coord.submit_review(people[0], leases[0], verdict="incorrect", failed=["fidelity"],
                            reason="off by one: the paper sums up to n, not n - 1")
    for rid, lease_id in zip(people[1:], leases[1:], strict=True):
        env.coord.submit_review(rid, lease_id, verdict="correct")
    assert env.coord.next_duty(people[0]) is None  # no PVV, and never on one's own claim
    duty = env.coord.next_duty(admin)
    assert duty is not None and duty.duty == "claim"
    with pytest.raises(CoordError, match="justification"):
        env.coord.resolve_claim(admin, duty.lease_id, confirmed=True, reason=" ")
    env.coord.resolve_claim(admin, duty.lease_id, confirmed=True, reason="checked: n = 0")
    assert env.coord.state.tickets[tid].status == "error"
    now = env.clock()
    finder = env.coord.state.trust(people[0], "analysis", now)
    misser = env.coord.state.trust(people[1], "analysis", now)
    assert finder.s.mean > 0.5 > misser.s.mean  # PVV-confirmed error: evidence on s


@pytest.mark.req("SR-11", "SR-13")
def test_acceptance_needs_a_pvv_review(tmp_path: Path) -> None:
    # A prior so low that three "correct" votes of newcomers already suffice.
    env = Env(tmp_path, params(decision=DecisionParams(prior_error=1e-4, delta_a=1e-3,
                                                       k_min=3, max_rounds=3),
                               rho_min=0.0, rho_max=0.0))  # no random re-checks
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 1))
    (tid,) = env.coord.state.tickets
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    people = env.people(3)
    for rid in people:
        lease_id = env.take(rid, tid)
        env.clock.advance(hours=1)
        env.coord.submit_review(rid, lease_id, verdict="correct")
    assert env.coord.state.tickets[tid].status == "open"
    assert env.events("pvv.requested")[-1]["reason"] == "decision"
    duty = env.coord.next_duty(admin)
    assert duty is not None and duty.duty == "pvv"
    env.coord.submit_review(admin, duty.lease_id, verdict="correct")
    assert env.coord.state.tickets[tid].status == "accepted"


@pytest.mark.req("SR-11")
def test_inconclusive_tickets_get_more_rounds_and_then_escalate(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 1))
    (tid,) = env.coord.state.tickets
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    for rid in env.people(6):  # newcomers carry no information: p stays at the prior
        lease_id = env.take(rid, tid)
        env.clock.advance(hours=1)
        env.coord.submit_review(rid, lease_id, verdict="correct")
        if (duty := env.coord.next_duty(admin)) is not None:
            env.coord.submit_review(admin, duty.lease_id, verdict="correct")
    rounds = [e["round"] for e in env.events("ticket.round_opened")]
    assert rounds == [2, 3]
    assert env.coord.state.tickets[tid].status == "escalate"
    env.coord.maintainer_decide(admin, tid, error=False, reason="read it myself")
    assert env.coord.state.tickets[tid].status == "accepted"


# --------------------------------------------------------------- honeypots
def _honeypot_env(tmp_path: Path, **kw: object) -> tuple[Env, str]:
    env = Env(tmp_path, params(honeypot_share=0.2, reveal_delay_s=86400, **kw))
    mutants = tmp_path / "mutants.jsonl"
    records = [{"kind": "header", "schema": "dpc.mutants/1", "toolchain": "x"}] + [
        Mutant(kind="mutant", decl=f"P.u{i}", target="type", operator="relation", detail="",
               type_correct=True, equivalent=False, proof_script=None,
               original=f"statement of P.u{i}", mutant=f"statement of P.u{i} (≤)",
               mutant_hash=str(i)).model_dump(mode="json") for i in range(8)]
    mutants.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    pool = HoneypotPool([MutantFileSource(mutants, Origin.PRIVATE_POOL, public=False)],
                        np.random.default_rng(1))
    sid = env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                                    tickets=specs("P", 8), pool=pool)
    return env, sid


def _work_through(env: Env, people: list[str], admin: str) -> None:
    """Honest reviewers: they find the planted errors and claim them."""
    for _ in range(200):
        progressed = False
        for rid in people:
            cs = env.coord.choice_set(rid)
            if cs is None:
                continue
            lease_id = env.coord.lease(rid, cs.set_id, cs.tickets[0]).lease_id
            env.clock.advance(minutes=20)
            tid = env.coord.state.leases[lease_id].ticket_id
            if env.vault.is_honeypot(tid):
                env.coord.submit_review(rid, lease_id, verdict="incorrect",
                                        reason="≤ where the paper has a strict <",
                                        failed=["fidelity"])
            else:
                env.coord.submit_review(rid, lease_id, verdict="correct")
            progressed = True
        while (duty := env.coord.next_duty(admin)) is not None:
            progressed = True
            if duty.duty == "claim":
                env.coord.resolve_claim(admin, duty.lease_id,
                                        confirmed=env.vault.is_honeypot(duty.ticket_id),
                                        reason="checked")
            else:
                env.coord.submit_review(admin, duty.lease_id, verdict="correct")
        if not progressed:
            return


@pytest.mark.req("SR-37", "SR-12")
def test_honeypots_are_revealed_late_in_batches_and_replace_soft_evidence(tmp_path: Path) -> None:
    env, _ = _honeypot_env(tmp_path, reveal_batch=2)
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    people = env.people(6)
    _work_through(env, people, admin)
    honeypots = [t for t in env.coord.state.tickets.values() if env.vault.is_honeypot(t.ticket_id)]
    assert len(honeypots) == 2 and all(t.status == "error" for t in honeypots)
    assert env.coord.tick()["revealed"] == 0  # not before the delay
    env.clock.advance(days=2)
    assert env.coord.tick()["revealed"] == 2
    st = env.coord.state
    for t in honeypots:
        assert t.honeypot is True
        for r in t.reviews:  # only hard evidence remains on revealed honeypots
            sources = {e.source for e in st.reviewers[r.reviewer].evidence
                       if e.ticket_id == t.ticket_id}
            assert sources == {Source.HONEYPOT}
    assert env.coord.stats()["planted_errors_revealed"] == 2
    finders = {r.reviewer for t in honeypots for r in t.reviews}
    assert all(st.reviewers[f].detections.honeypots_found >= 1 for f in finders)


def test_replaying_the_log_reproduces_the_state(tmp_path: Path) -> None:
    env, _ = _honeypot_env(tmp_path, reveal_batch=1)
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    people = env.people(5)
    _work_through(env, people, admin)
    env.clock.advance(days=2)
    env.coord.tick()
    replayed = env.make(seed=99)  # different RNG: replay must not depend on it
    now = env.clock()
    a, b = env.coord.state, replayed.state
    assert {t: (x.status, x.honeypot, x.round) for t, x in a.tickets.items()} == \
           {t: (x.status, x.honeypot, x.round) for t, x in b.tickets.items()}
    for rid in people:
        assert a.trust(rid, "analysis", now) == b.trust(rid, "analysis", now)
    assert len(env.events("coord.configured")) == 1  # unchanged parameters are not re-logged
    assert env.log.verify().ok


# --------------------------------------------------------------- attention
@pytest.mark.req("SR-38")
def test_attention_is_estimated_from_binding_choices(env: Env) -> None:
    for paper in "PQ":
        env.coord.open_submission(title=paper, repo_url="https://x", commit="c" * 40,
                                  tickets=specs(paper, 20))
    papers = {s.title: s.submission_id for s in env.coord.state.submissions.values()}
    for rid in env.people(16):
        cs = env.coord.choice_set(rid)
        assert cs is not None
        favourite = [t for t in cs.tickets
                     if env.coord.state.tickets[t].submission_id == papers["P"]]
        lease_id = env.coord.lease(rid, cs.set_id, (favourite or list(cs.tickets))[0]).lease_id
        env.clock.advance(minutes=30)
        env.coord.submit_review(rid, lease_id, verdict="correct")
    psi = env.coord.attention()
    assert psi[papers["P"]] > psi[papers["Q"]]


# --------------------------------------------------------------- throughput
@pytest.mark.req("SR-22")
@pytest.mark.slow
def test_two_thousand_reviews_a_week(tmp_path: Path) -> None:
    import time

    env = Env(tmp_path, params(pair_window_s=0))
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 600))
    people = env.people(60)
    start, done = time.perf_counter(), 0
    while done < 2000:
        for rid in people:
            cs = env.coord.choice_set(rid)
            if cs is None:
                continue
            lease_id = env.coord.lease(rid, cs.set_id, cs.tickets[0]).lease_id
            env.clock.advance(seconds=300)  # 2000 reviews in ~7 days
            env.coord.submit_review(rid, lease_id, verdict="correct")
            done += 1
    elapsed = time.perf_counter() - start
    assert elapsed < 120, f"{elapsed:.1f}s for 2000 reviews"
    assert env.coord.stats()["reviews_last_7_days"] >= 2000  # type: ignore[operator]


# ------------------------------------------------------------- tiers, preferences
def tiered(prefix: str, difficulties: list[float], domain: str = "analysis") -> list[TicketSpec]:
    return [TicketSpec(view(f"{prefix}.u{i}"), domain=domain, difficulty=b)
            for i, b in enumerate(difficulties)]


@pytest.mark.req("SR-27", "SR-38")
def test_the_choice_set_is_shown_at_the_limit_but_cannot_be_taken(env: Env) -> None:
    """Someone holding as many tickets as allowed still sees the set drawn for
    them (it is the same random set), but taking one waits until a ticket is
    returned or finished."""
    env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 3))
    env.coord.open_submission(title="Q", repo_url="https://x/q", commit="d" * 40,
                              tickets=specs("Q", 3))
    rid = env.people(1)[0]
    held = env.take(rid)
    cs = env.coord.choice_set(rid)
    assert cs is not None and cs.tickets
    with pytest.raises(Conflict, match="work-in-progress"):
        env.coord.lease(rid, cs.set_id, cs.tickets[0])
    env.coord.return_lease(rid, held)
    again = env.coord.choice_set(rid)
    assert again is not None and again.set_id == cs.set_id  # the same set, now usable
    env.coord.lease(rid, cs.set_id, cs.tickets[0])


def test_difficulty_tiers() -> None:
    assert [tier_of(b) for b in (-1.0, -0.5, 0.0, 0.5, 1.4, 1.5, 3.0)] == [
        "easy", "medium", "medium", "hard", "hard", "excellence", "excellence"]
    assert not tier_open("hard", roles=set(), maintainer=False)  # a group opens nothing
    assert tier_open("hard", roles={"PV"}, maintainer=False)
    assert not tier_open("excellence", roles={"PV"}, maintainer=False)
    assert tier_open("excellence", roles={"PV", "PVV"}, maintainer=False)
    assert tier_open("excellence", roles=set(), maintainer=True)


@pytest.mark.req("SR-05")
def test_hard_tickets_need_experience_until_they_have_waited_long(env: Env) -> None:
    big = "∀ ε > 0, ∃ δ > 0, ∀ x, ∃ y, " + "‖f x - f y‖ ≤ C / (1 + ‖x‖) ^ K ∧ " * 12 + "True"
    glossary = tuple(GlossaryEntry(name=f"Mathlib.c{i}", type="ℝ → ℝ", origin="library")
                     for i in range(12))
    hard_view = UnitView(declaration="P.big", decl_kind="theorem", components=(
        Component(target="type", text=big, glossary=glossary),))
    assert tier_of_view(hard_view) == "excellence"
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=[TicketSpec(hard_view, domain="analysis")])
    (tid,) = env.coord.state.tickets
    newcomer = env.people(1, "new", group="student")[0]
    expert = env.people(1, "exp", group="expert")[0]  # self-declared: opens nothing
    for rid in (newcomer, expert):
        reason = env.coord.why_not(rid, env.coord.state.tickets[tid], "review")
        assert reason is not None and "excellence" in reason
        assert env.coord.tiers_open(rid) == ["easy", "medium"]
    assert env.coord.choice_set(newcomer) is None
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    assert env.coord.why_not(admin, env.coord.state.tickets[tid], "review") is None
    env.clock.advance(days=15)  # waited past tier_gate_age_s: open to everyone (SR-05)
    assert env.coord.why_not(newcomer, env.coord.state.tickets[tid], "review") is None


@pytest.mark.req("SR-32", "SR-38")
def test_preferences_raise_the_chance_but_cannot_steer(tmp_path: Path) -> None:
    """Preferences fill at most half of a set, the rest is random, and they are
    ignored where the matching tickets come from a single paper (SR-38)."""
    env = Env(tmp_path, params(pair_window_s=0))
    for title, domain in (("P", "algebra"), ("Q", "algebra"), ("R", "analysis"),
                          ("S", "geometry"), ("T", "topology")):
        env.coord.open_submission(title=title, repo_url=f"https://x/{title}",
                                  commit=title.lower() * 40,
                                  tickets=tiered(title, [0.0, 0.0, 0.0], domain=domain))
    rid = env.people(1)[0]
    env.coord.set_preferences(rid, domains=["algebra"])  # two papers: applies
    cs = env.coord.choice_set(rid)
    assert cs is not None and len(cs.tickets) == 4
    domains = [env.coord.state.tickets[t].domain for t in cs.tickets]
    assert domains.count("algebra") >= 2  # raised: at random, 2 of 5 papers are algebra
    assert env.events("reviewer.preferences_set")[0]["domains"] == ["algebra"]
    chosen_by_preference = 0
    for _ in range(20):  # the other half stays random: no set is all algebra by force
        env.coord.set_preferences(rid, domains=["algebra"])
        drawn = env.coord.choice_set(rid)
        assert drawn is not None
        chosen_by_preference += sum(env.coord.state.tickets[t].domain == "algebra"
                                    for t in drawn.tickets)
    assert chosen_by_preference < 20 * 4
    env.coord.set_preferences(rid, domains=["analysis"])  # one paper only: ignored
    again = env.coord.choice_set(rid)
    assert again is not None and again.set_id != cs.set_id
    analysis = [t for t in again.tickets if env.coord.state.tickets[t].domain == "analysis"]
    assert len(analysis) <= 1  # one per paper, as without preferences
    with pytest.raises(CoordError, match="unknown tiers"):
        env.coord.set_preferences(rid, tiers=["legendary"])


def test_tiers_are_absolute_not_relative_to_the_submission() -> None:
    """A short lemma about natural numbers is easy in every submission; the
    relative difficulty b_i would call the average ticket of any paper medium."""
    small = UnitView(declaration="Mut.exists_gt", decl_kind="theorem", components=(
        Component(target="type", text="∀ (n : Nat), ∃ (m : Nat), n < m", glossary=(
            GlossaryEntry(name="Exists", type="…", origin="core"),
            GlossaryEntry(name="LT.lt", type="…", origin="core"),
            GlossaryEntry(name="Nat", type="Type", origin="core"))),))
    assert tier_of_view(small) == "easy"


@pytest.mark.req("SR-13")
def test_waiting_re_checks_are_counted_for_the_work_page(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 1))
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    rid = env.people(1)[0]
    assert env.coord.duties_waiting(admin) == 0
    lease = env.take(rid)
    env.clock.advance(minutes=20)
    env.coord.submit_review(rid, lease, verdict="incorrect", failed=["fidelity"],
                            reason="the paper states a strict inequality, the formal one does not")
    assert env.coord.duties_waiting(rid) == 0  # not the claimant's own claim, and no PVV role
    assert env.coord.duties_waiting(admin) == 1
    assert env.coord.next_duty(admin) is not None
    assert env.coord.duties_waiting(admin) == 0  # taken
