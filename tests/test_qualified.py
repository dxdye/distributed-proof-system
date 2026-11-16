"""Only qualified votes fill k_min; learner seats; deferred claims; the cap on
the external prior (review of 2026-11-16, decided by the project owner)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from dpc.coord import TicketSpec
from dpc.domain.decision import DecisionParams, Outcome, Vote, decide
from dpc.domain.trust import RoleThresholds, external_prior

from test_coord import Env, params, view

REASON = "the formal statement drops a hypothesis the paper states"


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params(qualified_seats=True, learner_slots=1))
    yield e
    e.log.close()
    e.vault.close()


def open_units(env: Env, n: int) -> str:
    return env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                     tickets=[TicketSpec(view(f"P.u{i}"), domain="analysis")
                                              for i in range(n)])


def test_k_min_counts_only_qualified_votes() -> None:
    params = DecisionParams(prior_error=0.02, delta_a=1e-3, k_min=3)
    sure = [Vote(f"q{i}", False, 0.95, 0.999) for i in range(2)]
    learners = [Vote(f"l{i}", False, 0.95, 0.999, qualified=False) for i in range(5)]
    d = decide(sure + learners, params, pvv_reviewed=True)
    assert d.outcome is Outcome.MORE_REVIEWS and d.independent_votes == 2
    d = decide([*sure, Vote("q2", False, 0.95, 0.999)], params, pvv_reviewed=True)
    assert d.outcome is Outcome.ACCEPTED


@pytest.mark.req("SR-28")
def test_newcomers_review_on_learner_seats_and_never_fill_k_min(tmp_path: Path) -> None:
    """Only the counting matters here: with a prior below δ_A the ticket is
    accepted as soon as k_min qualified votes and a PVV are in. (Founding
    maintainers hold the roles but no measured weight, C-42.)"""
    env = Env(tmp_path, params(qualified_seats=True, learner_slots=1, decision=DecisionParams(
        prior_error=5e-4, delta_a=1e-3, k_min=3, max_rounds=3)))
    sid = open_units(env, 1)
    ticket = env.coord.real_ticket(sid, "P.u0")
    assert ticket is not None
    first, second = env.people(2, "new")
    lease = env.take(first)
    assert "no free learner seat" in (env.coord.why_not(second, ticket, "review") or "")
    env.clock.advance(minutes=20)
    env.coord.submit_review(first, lease, verdict="correct")
    founders = [env.maintainer(r) for r in env.people(3, "founder")]  # PV and PVV
    for rid in founders[:2]:
        lease = env.take(rid)
        env.clock.advance(minutes=20)
        env.coord.submit_review(rid, lease, verdict="correct")
    assert ticket.status == "open"  # one learner and two qualified: k_min = 3 not reached
    lease = env.take(founders[2])
    env.clock.advance(minutes=20)
    env.coord.submit_review(founders[2], lease, verdict="correct")
    checker = env.maintainer(env.people(1, "checker")[0])  # sampled re-checks, if any
    while (duty := env.coord.next_duty(checker)) is not None:
        env.clock.advance(minutes=20)
        env.coord.submit_review(checker, duty.lease_id, verdict="correct")
    assert ticket.status == "accepted"
    env.log.close()
    env.vault.close()


def test_a_learner_blocks_with_one_claim_at_a_time(env: Env) -> None:
    sid = open_units(env, 2)
    learner = env.people(1, "new")[0]
    for _ in range(2):
        lease = env.take(learner)
        env.clock.advance(minutes=20)
        env.coord.submit_review(learner, lease, verdict="incorrect", failed=["fidelity"],
                                reason=REASON)
    claims = sorted(env.coord.state.claims.values(), key=lambda c: c.opened)
    assert [c.status for c in claims] == ["open", "deferred"]
    deferred_ticket = env.coord.state.tickets[claims[1].ticket_id]
    assert not any(env.coord.state.claims[c].status == "open" for c in deferred_ticket.claims)
    pvv = env.maintainer(env.people(1, "founder")[0])
    duty = env.coord.next_duty(pvv)
    assert duty is not None and duty.duty == "claim" and duty.claim_id == claims[0].claim_id
    env.clock.advance(minutes=10)
    env.coord.resolve_claim(pvv, duty.lease_id, confirmed=False, reason="the hypothesis is there")
    assert env.coord.state.claims[claims[1].claim_id].status == "open"  # its turn now
    _ = sid


def test_a_deferred_finding_on_a_decided_ticket_goes_to_the_maintainers(env: Env) -> None:
    sid = open_units(env, 2)
    learner = env.people(1, "new")[0]
    for _ in range(2):
        lease = env.take(learner)
        env.clock.advance(minutes=20)
        env.coord.submit_review(learner, lease, verdict="incorrect", failed=["fidelity"],
                                reason=REASON)
    first, deferred = sorted(env.coord.state.claims.values(), key=lambda c: c.opened)
    env.coord.state.tickets[deferred.ticket_id].status = "accepted"  # (shortcut)
    pvv = env.maintainer(env.people(1, "founder")[0])
    duty = env.coord.next_duty(pvv)
    assert duty is not None and duty.claim_id == first.claim_id
    env.coord.resolve_claim(pvv, duty.lease_id, confirmed=True, reason="confirmed: it is missing")
    assert env.coord.state.claims[deferred.claim_id].status == "reopen"
    request = next(iter(env.coord.state.reopens.values()))
    assert request.ticket_id == deferred.ticket_id and request.reason.startswith("deferred")
    _ = sid


def test_a_profile_alone_never_makes_anyone_qualified() -> None:
    """a_max = 1: a "correct" vote moves the odds by at most a factor 2, and
    the lower bound stays below θ_PV (decided 2026-11-16)."""
    prior = external_prior({"orcid": 1e6, "github": 1e6}, {"orcid": 1.0, "github": 1.0})
    s, c = prior.point_estimates()
    assert (1 - s) / c >= 0.5 - 1e-9  # the odds fall by at most a factor 2
    assert "PV" not in RoleThresholds().roles(prior)
