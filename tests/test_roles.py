"""Roles earned and appointed, kept apart (proposal C-42); root testers."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from dpc.coord import Conflict, CoordError, Forbidden, TicketSpec

from test_coord import Env, params, specs, view


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


def open_two_domains(env: Env) -> str:
    tickets = [TicketSpec(view("P.a"), domain="analysis"),
               TicketSpec(view("P.b"), domain="algebra")]
    return env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                     tickets=tickets)


@pytest.mark.req("SR-35")
def test_administrators_run_the_platform_and_review_nothing(env: Env) -> None:
    sid = open_two_domains(env)
    admin = env.admin()
    st = env.coord.state
    assert "PVV" not in st.roles(admin, "analysis", env.coord.now())
    real = env.coord.real_ticket(sid, "P.a")
    assert real is not None
    assert "administrators do not review" in (env.coord.why_not(admin, real, "review") or "")
    assert env.coord.choice_set(admin) is None or not env.coord.choice_set(admin).tickets
    with pytest.raises(Conflict, match="administrators are not maintainers"):
        env.coord.appoint_maintainer(admin, admin, ["analysis"], reason="no, not like this",
                                     founding=True)


def test_older_logs_name_the_administrator_maintainer(env: Env) -> None:
    rid = env.people(1)[0]
    env.log.append("reviewer.maintainer_appointed", {"reviewer": rid, "by": "operator"})
    assert env.make().state.reviewers[rid].admin


@pytest.mark.req("SR-35")
def test_maintainers_need_measured_pvv_or_a_founding_term(env: Env) -> None:
    open_two_domains(env)
    admin = env.admin()
    rid = env.people(1)[0]
    with pytest.raises(Conflict, match="not PVV in analysis"):
        env.coord.appoint_maintainer(admin, rid, ["analysis"], reason="knows the field well")
    with pytest.raises(CoordError, match="reason"):
        env.coord.appoint_maintainer(admin, rid, ["analysis"], reason="ok", founding=True)
    with pytest.raises(Forbidden):  # only administrators appoint
        env.coord.appoint_maintainer(rid, rid, ["analysis"], reason="appointing myself",
                                     founding=True)
    env.coord.appoint_maintainer(admin, rid, ["analysis"], reason="founding the domain",
                                 until=env.coord.now() + timedelta(days=30), founding=True)
    st, now = env.coord.state, env.coord.now()
    assert {"PVV", "maintainer"} <= st.roles(rid, "analysis", now)
    assert "PVV" not in st.roles(rid, "algebra", now)  # only where appointed
    env.clock.advance(days=31)  # the founding term is over: measured trust only
    assert "PVV" not in st.roles(rid, "analysis", env.coord.now())
    assert not st.maintains(rid, "analysis", env.coord.now())


def test_a_maintainer_acts_only_in_their_domains(env: Env) -> None:
    sid = open_two_domains(env)
    rid = env.maintainer(env.people(1)[0], "algebra")
    real = env.coord.real_ticket(sid, "P.a")  # analysis
    assert real is not None
    real.status = "escalate"  # (shortcut: escalation is tested elsewhere)
    with pytest.raises(Forbidden, match="this domain"):
        env.coord.maintainer_decide(rid, real.ticket_id, error=False, reason="looks fine to me")
    with pytest.raises(Forbidden):
        env.coord.close_submission(rid, sid)  # administrators only
    env.coord.revoke_maintainer(env.admin(), rid, [], reason="end of the founding phase")
    assert not env.coord.state.maintained(rid, env.coord.now())


@pytest.mark.req("SR-06")
def test_the_maintainer_view_counts_as_having_seen_the_original(env: Env) -> None:
    sid = open_two_domains(env)
    rid = env.maintainer(env.people(1)[0], "analysis")
    env.coord.maintainer_view(rid, sid, "P.a")
    assert (sid, "P.a") in env.coord.state.seen_units[rid]
    real = env.coord.real_ticket(sid, "P.a")
    assert real is not None and env.coord.why_not(rid, real, "review") is not None
    with pytest.raises(Forbidden):
        env.coord.maintainer_view(rid, sid, "P.b")  # algebra: not theirs


def test_root_testers_only_where_the_parameters_allow_them(tmp_path: Path) -> None:
    env = Env(tmp_path, params())
    rid = env.people(1, "root")[0]
    with pytest.raises(Forbidden, match="switched off"):
        env.coord.appoint_root(rid)
    env.log.close()
    env.vault.close()

    (tmp_path / "test").mkdir()
    env = Env(tmp_path / "test", params(root_accounts=True, tier_gating=True))
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=[TicketSpec(view("P.h"), domain="analysis",
                                                        difficulty=3.0), *specs("P", 2)])
    rid = env.people(1, "root")[0]
    env.coord.appoint_root(rid)
    st, now = env.coord.state, env.coord.now()
    assert {"PV", "PVV", "maintainer", "admin"} <= st.roles(rid, "analysis", now)
    hard = env.coord.real_ticket(sid, "P.h")
    assert hard is not None and env.coord.why_not(rid, hard, "review") is None  # no tiers
    assert env.coord.preference_changes(rid) == (None, None)  # no limits
    env.coord.tag_submission(rid, sid, ["root-test"])  # maintainer work
    env.coord.maintainer_view(rid, sid, "P.u1")
    real = env.coord.real_ticket(sid, "P.u1")
    assert real is not None and env.coord.why_not(rid, real, "review") is None  # not bound
    env.coord.close_submission(rid, sid)  # administrator work
    env.log.close()
    env.vault.close()
