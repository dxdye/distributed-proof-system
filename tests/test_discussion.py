"""Discussion after the decision (proposal C-25, S-21, S-22)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dpc.api import create_app
from dpc.coord import Conflict, CoordError, Forbidden, NotFound
from dpc.honeypots import HoneypotPool, MutantFileSource, Origin

from test_coord import Env, params, specs

REASON = "the paper states a strict inequality here, the formal statement does not"


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


def decide_error(env: Env, admin: str, rid: str) -> str:
    """One reviewer claims an error, a maintainer (counts as PVV) confirms it."""
    lease = env.take(rid)
    tid = env.coord.state.leases[lease].ticket_id
    env.clock.advance(minutes=20)
    env.coord.submit_review(rid, lease, verdict="incorrect", failed=["fidelity"], reason=REASON)
    duty = env.coord.next_duty(admin)
    assert duty is not None and duty.duty == "claim"
    env.coord.resolve_claim(admin, duty.lease_id, confirmed=True, reason="agreed: strict")
    assert env.coord.state.tickets[tid].status == "error"
    return tid


def setup(env: Env) -> tuple[str, str, str, str]:
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 1))
    admin = env.people(1, "admin")[0]
    env.maintainer(admin)
    rid = env.people(1)[0]
    return sid, "P.u0", admin, rid


@pytest.mark.req("SR-23")
def test_threads_open_after_the_decision_and_posts_are_anonymous(env: Env) -> None:
    sid, decl, admin, rid = setup(env)
    other = env.people(1, "other")[0]
    assert not env.coord.thread_open(sid, decl)
    with pytest.raises(Forbidden, match="opens once"):
        env.coord.post(other, sid, decl, "Too early.")
    decide_error(env, admin, rid)
    assert env.coord.thread_open(sid, decl)
    env.coord.share_review(rid, sid, decl)
    with pytest.raises(NotFound):
        env.coord.share_review(rid, sid, decl)  # shared already
    env.coord.post(other, sid, decl, "Good catch: the paper says < on p. 3.")
    env.coord.post(admin, sid, decl, "Confirmed by the maintainers.", show_pseudonym=True)
    client = TestClient(create_app(env.coord, tick_seconds=None))
    _, token = env.coord.register("reader", notice_acknowledged=True)
    auth = {"Authorization": f"Bearer {token}"}
    thread = client.get("/api/thread", params={"submission_id": sid, "declaration": decl},
                        headers=auth).json()
    by_kind = {p["kind"]: p for p in thread["posts"]}
    assert by_kind["review"]["author"] == "Reviewer A"  # anonymous by default
    assert by_kind["review"]["verdict"] == "incorrect" and by_kind["review"]["reviewed_here"]
    authors = {p["author"] for p in thread["posts"]}
    # The maintainer chose to show the pseudonym:
    assert {"Reviewer A", "Reviewer B", "admin0"} == authors
    maint = next(p for p in thread["posts"] if p["author"] == "admin0")
    assert maint["maintainer"] is True and maint["member_since"] == "2026-11"
    assert thread["outcome"] == "error" and thread["me"]["label"] is None
    listing = client.get("/api/discussions", headers=auth).json()
    assert listing[0]["declaration"] == decl and listing[0]["posts"] == 3
    # The log never holds a pseudonym (SR-23).
    assert all("reader" not in json.dumps(e.payload) for e in env.log.entries())


@pytest.mark.req("SR-06", "SR-37")
def test_no_thread_while_a_planted_error_of_the_submission_is_unrevealed(tmp_path: Path) -> None:
    """Per declaration, the opening time would show which declaration still has
    an open planted copy; so threads wait for every planted error."""
    env = Env(tmp_path, params(honeypot_share=0.2))
    mutants = tmp_path / "mutants.jsonl"
    records = [{"kind": "header", "schema": "dpc.mutants/1", "toolchain": "x"}] + [
        {"kind": "mutant", "decl": f"P.u{i}", "target": "type", "operator": "relation",
         "detail": "", "type_correct": True, "equivalent": False, "proof_script": None,
         "original": f"statement of P.u{i}", "mutant": f"mutated P.u{i}", "mutant_hash": str(i)}
        for i in range(4)]
    mutants.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    pool = HoneypotPool([MutantFileSource(mutants, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(0))
    sid = env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                                    tickets=specs("P", 4), pool=pool)
    admin = env.people(1, "admin")[0]
    env.coord.appoint_admin(admin)
    planted = {t for t in env.coord.state.tickets if env.vault.is_honeypot(t)}
    assert len(planted) == 1
    decl = next(t.view.declaration for t in env.coord.state.tickets.values()
                if t.ticket_id not in planted)
    for t in env.coord.unit_tickets(sid, decl):  # decide every ticket of the declaration
        t.status = "accepted"  # (shortcut: the decision rule is tested elsewhere)
    assert not env.coord.thread_open(sid, decl)
    env.coord.close_submission(admin, sid)  # reveals every commitment
    assert env.coord.thread_open(sid, decl)


def test_reviews_of_planted_errors_are_not_shared(env: Env, tmp_path: Path) -> None:
    sid, decl, admin, rid = setup(env)
    decide_error(env, admin, rid)
    real = env.coord.real_ticket(sid, decl)
    assert real is not None and real.honeypot is not True
    review = env.coord.shareable_review(rid, sid, decl)
    assert review is not None and review.ticket_id == real.ticket_id


@pytest.mark.req("SR-12")
def test_votes_sort_but_never_change_trust(env: Env) -> None:
    sid, decl, admin, rid = setup(env)
    decide_error(env, admin, rid)
    pid = env.coord.share_review(rid, sid, decl)
    voters = env.people(3, "voter")
    domain = env.coord.state.tickets[env.coord.real_ticket(sid, decl).ticket_id].domain  # type: ignore[union-attr]
    before = env.coord.state.trust(rid, domain, env.coord.now())
    for v in voters:
        env.coord.vote(v, pid, 1)
    env.coord.vote(voters[0], pid, -1)  # a vote can be changed
    assert env.coord.state.posts[pid].score == 1
    assert env.coord.state.trust(rid, domain, env.coord.now()) == before
    with pytest.raises(CoordError, match="own post"):
        env.coord.vote(rid, pid, 1)


def test_reopen_request_becomes_an_escalation_only_through_a_maintainer(env: Env) -> None:
    sid, decl, admin, rid = setup(env)
    tid = decide_error(env, admin, rid)
    other = env.people(1, "other")[0]
    with pytest.raises(CoordError, match="at least"):
        env.coord.request_reopen(other, sid, decl, "wrong")
    qid = env.coord.request_reopen(other, sid, decl, "The paper uses ≤ in the published "
                                                     "version; the strict bound was a typo.")
    with pytest.raises(Conflict):
        env.coord.request_reopen(other, sid, decl, "Once more, the same request in other words.")
    assert env.coord.state.tickets[tid].status == "error"  # discussion never decides
    with pytest.raises(Forbidden):
        env.coord.resolve_reopen(other, qid, reopen=True, reason="me")
    env.coord.resolve_reopen(admin, qid, reopen=True, reason="the published version uses ≤")
    assert env.coord.state.tickets[tid].status == "escalate"
    assert not env.coord.thread_open(sid, decl)  # undecided again: the thread closes
    env.coord.maintainer_decide(admin, tid, error=False, reason="faithful to the final version")
    assert env.coord.state.tickets[tid].status == "accepted"


def test_reported_posts_can_be_hidden_by_maintainers(env: Env) -> None:
    sid, decl, admin, rid = setup(env)
    decide_error(env, admin, rid)
    other = env.people(1, "other")[0]
    pid = env.coord.post(other, sid, decl, "Off topic, and rude.")
    env.coord.report_post(rid, pid, "rude")
    with pytest.raises(Forbidden):
        env.coord.hide_post(other, pid, "no")
    env.coord.hide_post(admin, pid, "rude")
    assert env.coord.state.posts[pid].hidden == "rude"


@pytest.mark.req("SR-12")
def test_votes_on_a_thread_sort_the_list_and_say_nothing_about_the_decision(env: Env) -> None:
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 2))
    admin = env.people(1, "admin")[0]
    env.maintainer(admin)
    first, second = env.people(2)
    voter = env.people(1, "voter")[0]
    with pytest.raises(Forbidden, match="opens once"):
        env.coord.vote_thread(voter, sid, "P.u0", 1)
    decide_error(env, admin, first)
    decide_error(env, admin, second)
    assert len(env.coord.open_threads()) == 2
    domain = env.coord.state.tickets[env.coord.state.submissions[sid].tickets[0]].domain
    before = env.coord.state.trust(first, domain, env.coord.now())
    env.coord.vote_thread(voter, sid, "P.u1", 1)
    assert env.coord.state.trust(first, domain, env.coord.now()) == before
    with pytest.raises(CoordError):
        env.coord.vote_thread(voter, sid, "P.u1", 2)
    client = TestClient(create_app(env.coord, tick_seconds=None))
    _, token = env.coord.register("reader", notice_acknowledged=True)
    auth = {"Authorization": f"Bearer {token}"}
    listing = client.get("/api/discussions", headers=auth).json()
    assert [t["declaration"] for t in listing] == ["P.u1", "P.u0"]  # worth reading first
    assert listing[0]["score"] == 1 and listing[0]["my_vote"] == 0
    assert client.post("/api/thread/vote", headers=auth, json={
        "submission_id": sid, "declaration": "P.u0", "value": -1}).json()["ok"]
    thread = client.get("/api/thread", params={"submission_id": sid, "declaration": "P.u0"},
                        headers=auth).json()
    assert thread["score"] == -1 and thread["my_vote"] == -1
    assert env.coord.state.tickets[env.coord.real_ticket(sid, "P.u0").ticket_id].status \
        == "error"  # type: ignore[union-attr]


def test_a_report_can_be_withdrawn(env: Env) -> None:
    sid, decl, admin, rid = setup(env)
    decide_error(env, admin, rid)
    other = env.people(1, "other")[0]
    pid = env.coord.post(other, sid, decl, "A comment someone may find rude.")
    env.coord.report_post(rid, pid, "rude")
    with pytest.raises(Conflict, match="already reported"):
        env.coord.report_post(rid, pid, "still rude")
    client = TestClient(create_app(env.coord, tick_seconds=None))
    _, token = env.coord.register("reporter", notice_acknowledged=True)
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/api/posts/{pid}/report", headers=auth,
                       json={"reason": "off topic"}).json()["ok"]
    params = {"submission_id": sid, "declaration": decl}
    post = client.get("/api/thread", params=params, headers=auth).json()["posts"][0]
    assert post["reported_by_me"] is True
    assert client.delete(f"/api/posts/{pid}/report", headers=auth).json()["ok"]
    post = client.get("/api/thread", params=params, headers=auth).json()["posts"][0]
    assert post["reported_by_me"] is False
    assert client.delete(f"/api/posts/{pid}/report", headers=auth).status_code == 404
    env.coord.withdraw_report(rid, pid)
    assert env.coord.state.posts[pid].reports == []
