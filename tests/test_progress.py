"""The public progress page (proposal C-26, S-23)."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_discussion import decide_error

from dpc.api import create_app
from dpc.coord import Forbidden, TicketSpec, progress
from dpc.honeypots import HoneypotPool, MutantFileSource, Origin
from dpc.tickets.paper import PaperPassage, PaperSource

from test_coord import Env, params, specs, view

PASSAGE = PaperPassage(source=PaperSource(title="On P", url="https://arxiv.org/abs/0000.00000"),
                       locator="Theorem 1, p. 2", statement="For all $n$, $P(n)$ holds.",
                       mapped_by="maintainer")


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


def open_paper(env: Env, n: int) -> str:
    tickets = [TicketSpec(view("P.u0"), domain="analysis", paper=PASSAGE), *specs("P", n)[1:]]
    return env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                     tickets=tickets, root="P.u0")


def planted_env(tmp_path: Path) -> Env:
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
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs("P", 4), pool=pool, root="P.u0")
    return env


@pytest.mark.req("SR-42", "SR-06")
def test_counts_are_by_declaration_and_wait_for_every_ticket(tmp_path: Path) -> None:
    """Ticket counts would expose the planted errors; a declaration decided
    before its planted copy would tell the copy's holder that it is planted."""
    env = planted_env(tmp_path)
    sid = next(iter(env.coord.state.submissions))
    assert len(env.coord.state.tickets) == 5  # four declarations, one planted copy
    planted = next(t for t in env.coord.state.tickets.values()
                   if env.vault.is_honeypot(t.ticket_id))
    real = next(t for t in env.coord.unit_tickets(sid, planted.view.declaration)
                if t is not planted)
    real.status = "accepted"  # (shortcut: the decision rule is tested elsewhere)
    s = progress.summary(env.coord, sid)
    assert s["declarations"] == 4 and s["decided"] == 0 and s["coverage"] == 0.0
    planted.status = "error"
    s = progress.summary(env.coord, sid)
    assert s["decided"] == 1 and s["accepted"] == 1 and s["errors"] == 0  # the real verdict
    # Nothing on the page names a ticket, and the public statistics count no
    # tickets: tickets minus declarations would be the number of planted errors.
    page = json.dumps(progress.detail(env.coord, sid, None))
    assert "ticket" not in page and all(t not in page for t in env.coord.state.tickets)
    assert not any("ticket" in k for k in env.coord.stats())
    env.log.close()
    env.vault.close()


@pytest.mark.req("SR-42", "SR-53")
def test_prl_and_the_residual_error(env: Env) -> None:
    sid = open_paper(env, 3)
    tickets = [env.coord.state.tickets[t] for t in env.coord.state.submissions[sid].tickets]
    by_decl = {t.view.declaration: t for t in tickets}
    assert progress.summary(env.coord, sid)["prl"] == 1  # opened: formalized and built
    by_decl["P.u0"].status, by_decl["P.u0"].p_error = "accepted", 0.01
    s = progress.summary(env.coord, sid)
    assert s["prl"] == 2 and s["residual_error"] == pytest.approx(0.01)
    for t in tickets:
        t.status, t.p_error = "accepted", 0.01
    s = progress.summary(env.coord, sid)
    assert s["prl"] == 3 and s["coverage"] == 1.0
    assert s["residual_error"] == pytest.approx(1 - 0.99 ** 3)
    by_decl["P.u2"].status = "error"  # a confirmed finding caps the result
    s = progress.summary(env.coord, sid)
    assert s["prl"] == 1 and s["errors"] == 1
    assert s["residual_error"] == pytest.approx(1 - 0.99 ** 2)
    assert s["forecast"] is None  # no measured throughput yet
    assert not math.isnan(s["coverage"])


@pytest.mark.req("SR-06")
def test_the_lean_statement_waits_for_the_decision(env: Env) -> None:
    sid = open_paper(env, 1)
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    rid = env.people(1)[0]
    d = progress.detail(env.coord, sid, None)
    assert d["main_statement"] == PASSAGE.statement and d["main_locator"] == PASSAGE.locator
    assert d["paper_url"] == PASSAGE.source.url
    assert d["main_view"] is None  # the paper's statement, not the formal one, until decided
    assert [u["state"] for u in d["units"]] == ["not started"]
    decide_error(env, admin, rid)
    d = progress.detail(env.coord, sid, None)
    assert d["main_view"]["declaration"] == "P.u0"
    assert d["units"][0] == {"declaration": "P.u0", "decl_kind": "theorem", "tier": "easy",
                             "domain": "analysis", "state": "error", "discussion": True}
    assert [p["decided"] for p in d["timeline"]] == [0, 1, 1]


@pytest.mark.req("SR-42")
def test_anyone_reads_the_page_and_only_maintainers_write_notes(env: Env) -> None:
    sid = open_paper(env, 2)
    admin, admin_token = env.coord.register("admin", notice_acknowledged=True)
    env.coord.appoint_maintainer(admin)
    _, token = env.coord.register("reader", notice_acknowledged=True)
    client = TestClient(create_app(env.coord, tick_seconds=None))
    listing = client.get("/api/progress")
    assert listing.status_code == 200 and listing.json()[0]["submission_id"] == sid
    assert client.get(f"/api/progress/{sid}").status_code == 200
    assert client.get("/api/progress/S-none").status_code == 404
    note = {"text": "Class A is half done; the hard lemmas are next."}
    assert client.post(f"/api/progress/{sid}/notes", json=note).status_code == 401
    reader = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/api/progress/{sid}/notes", json=note, headers=reader).status_code == 403
    with pytest.raises(Forbidden):
        env.coord.post(env.people(1)[0], sid, "", "not a maintainer")
    r = client.post(f"/api/progress/{sid}/notes", json=note,
                    headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    pid = r.json()["post_id"]
    assert client.post(f"/api/posts/{pid}/vote", json={"value": 1}, headers=reader).json()["ok"]
    mine = client.get(f"/api/progress/{sid}", headers=reader).json()["notes"]
    assert mine[0]["author"] == "Maintainer A" and mine[0]["maintainer"] is True
    assert mine[0]["score"] == 1 and mine[0]["my_vote"] == 1
    public = client.get(f"/api/progress/{sid}").json()["notes"]
    assert public[0]["my_vote"] == 0 and public[0]["text"] == note["text"]
    # Notes are not a discussion of a declaration.
    assert client.get("/api/discussions", headers=reader).json() == []
