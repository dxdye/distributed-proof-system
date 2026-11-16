"""Hashtags of a submission (proposal C-44): for finding a problem, never for the draw."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_discussion import decide_error

from dpc.api import create_app
from dpc.coord import CoordError, Forbidden
from dpc.coord.tags import MAX_TAGS, normalize_tag, normalize_tags

from test_coord import Env, params, specs


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


def test_tags_are_normalized() -> None:
    assert normalize_tag("#Erdős Problems") == "erdos-problems"
    assert normalize_tag(" navier_stokes ") == "navier-stokes"
    assert normalize_tags(["#Counterexample", "counterexample", "", "#", "k-pi-1"]) == (
        "counterexample", "k-pi-1")
    for bad in ["a", "-x", "x-", "a--b", "ζ(s)", "x" * 41, "two#tags"]:
        with pytest.raises(ValueError, match="not a tag"):
            normalize_tag(bad)
    with pytest.raises(ValueError, match=f"at most {MAX_TAGS}"):
        normalize_tags([f"t{i}" for i in range(MAX_TAGS + 1)])


@pytest.mark.req("SR-42")
def test_maintainers_tag_a_submission(env: Env) -> None:
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 2), tags=["#Navier Stokes", "pde"])
    assert env.coord.state.submissions[sid].tags == ("navier-stokes", "pde")
    admin = env.people(1, "admin")[0]
    rid = env.people(1)[0]
    with pytest.raises(Forbidden):
        env.coord.tag_submission(rid, sid, ["spam"])
    env.maintainer(admin)
    assert env.coord.tag_submission(admin, sid, ["millennium-prize", "Navier-Stokes"]) == (
        "millennium-prize", "navier-stokes")
    seq = env.coord.state.seq
    env.coord.tag_submission(admin, sid, ["millennium-prize", "navier-stokes"])
    assert env.coord.state.seq == seq  # unchanged: no event
    with pytest.raises(CoordError, match="not a tag"):
        env.coord.tag_submission(admin, sid, ["ζ(s)"])
    # The state is rebuilt from the log alone.
    assert env.make().state.submissions[sid].tags == ("millennium-prize", "navier-stokes")


@pytest.mark.req("SR-42")
def test_tags_appear_on_the_progress_page_and_in_the_discussions(env: Env) -> None:
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 1), tags=["counterexample"])
    admin, admin_token = env.coord.register("boss", notice_acknowledged=True)
    env.maintainer(admin)
    decide_error(env, admin, env.people(1)[0])
    client = TestClient(create_app(env.coord, tick_seconds=None))
    assert client.get("/api/progress").json()[0]["tags"] == ["counterexample"]
    _, token = env.coord.register("reader", notice_acknowledged=True)
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/discussions", headers=auth).json()[0]["tags"] == ["counterexample"]
    thread = client.get("/api/thread", params={"submission_id": sid, "declaration": "P.u0"},
                        headers=auth).json()
    assert thread["tags"] == ["counterexample"]
    # Only maintainers set them.
    denied = client.post(f"/api/admin/submissions/{sid}/tags", headers=auth,
                         json={"tags": ["spam"]})
    assert denied.status_code == 403
    ok = client.post(f"/api/admin/submissions/{sid}/tags",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={"tags": ["#Seymour", "digraphs"]})
    assert ok.json() == {"tags": ["seymour", "digraphs"]}
    bad = client.post(f"/api/admin/submissions/{sid}/tags",
                      headers={"Authorization": f"Bearer {admin_token}"}, json={"tags": ["ζ"]})
    assert bad.status_code == 400
