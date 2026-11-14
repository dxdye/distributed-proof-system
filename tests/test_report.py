"""Reports on a submission (concept §11.1, §16; SR-17, SR-42, SR-47)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_progress import open_paper, planted_env

from dpc.__main__ import main
from dpc.api import create_app
from dpc.coord import report

from test_coord import Env, params

#: The overrides of test_coord.params(), as the service's parameter file.
PARAMS = {"pair_window_s": 0, "honeypot_share": 0.0, "t_min_s": 60.0,
          "decision": {"prior_error": 0.02, "delta_a": 1e-3, "k_min": 3, "max_rounds": 3}}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


@pytest.mark.req("SR-42", "SR-47")
def test_the_report_says_what_the_progress_page_says(env: Env) -> None:
    sid = open_paper(env, 3)
    text = report.render(env.coord, sid)
    assert text.startswith("# Review report: P\n")
    assert "Interim report as of" in text and "not signed (pilot)" in text
    assert "| Readiness | PRL 1:" in text
    assert "0 of 3 declarations decided" in text
    assert "> For all $n$, $P(n)$ holds." in text  # the paper's statement
    assert "published once it is decided" in text  # the Lean statement waits
    assert "| `P.u0` | theorem |" in text
    head = env.log.head()
    assert head is not None and head.hash in text  # checkable against the log


@pytest.mark.req("SR-42", "SR-06")
def test_the_report_names_no_planted_copy(tmp_path: Path) -> None:
    env = planted_env(tmp_path)
    sid = next(iter(env.coord.state.submissions))
    text = report.render(env.coord, sid)
    assert "mutated" not in text
    assert not any(tid in text for tid in env.coord.state.tickets)
    # four declarations, five tickets: only declarations are counted
    assert "0 of 4 declarations decided" in text and "of 5" not in text
    env.log.close()
    env.vault.close()


@pytest.mark.req("SR-17")
def test_the_same_log_gives_the_same_report_and_stays_as_it_is(env: Env, tmp_path: Path) -> None:
    sid = open_paper(env, 2)
    head = env.log.head()
    settings = tmp_path / "params.json"
    settings.write_text(json.dumps(PARAMS), "utf-8")
    args = ["report", sid, "--data", str(tmp_path), "--log", str(tmp_path / "log.sqlite"),
            "--params", str(settings)]
    assert main([*args, "--out", str(tmp_path / "a.md")]) == 0
    assert main([*args, "--out", str(tmp_path / "b.md")]) == 0
    assert (tmp_path / "a.md").read_text("utf-8") == (tmp_path / "b.md").read_text("utf-8")
    # Other parameters would append a configuration event: refused, nothing written.
    assert main(["report", sid, "--data", str(tmp_path), "--log",
                 str(tmp_path / "log.sqlite"), "--out", str(tmp_path / "c.md")]) == 2
    assert env.log.head() == head and not (tmp_path / "c.md").exists()


@pytest.mark.req("SR-47")
def test_the_report_is_public(env: Env) -> None:
    sid = open_paper(env, 2)
    client = TestClient(create_app(env.coord, tick_seconds=None))
    r = client.get(f"/api/progress/{sid}/report")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# Review report: P")
    assert client.get("/api/progress/S-none/report").status_code == 404
