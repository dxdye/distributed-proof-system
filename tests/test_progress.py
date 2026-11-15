"""The public progress page (proposal C-26, S-23)."""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_discussion import decide_error

from dpc.api import create_app
from dpc.audit import AuditLog
from dpc.coord import Forbidden, TicketSpec, progress
from dpc.coord import events as ev
from dpc.honeypots import HoneypotPool, MutantFileSource, Origin
from dpc.ingest.basis import trust_basis
from dpc.tickets.paper import PaperPassage, PaperSource
from dpc.tickets.views import Component, GlossaryEntry, UnitView

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


@pytest.mark.req("SR-42")
def test_a_submission_opened_again_replaces_the_closed_one(env: Env) -> None:
    """A paper map cannot change on an open submission; a maintainer closes it
    and opens it again. The page then shows the new one as current."""
    old = open_paper(env, 2)
    env.clock.advance(minutes=5)
    other = env.coord.open_submission(title="Q", repo_url="https://x/q", commit="c" * 40,
                                      tickets=specs("Q", 2), root="Q.u0")
    assert progress.summary(env.coord, old)["replaced_by"] is None  # still open
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    env.coord.close_submission(admin, old)
    assert progress.summary(env.coord, old)["replaced_by"] is None  # closed, not reopened
    env.clock.advance(minutes=5)
    new = open_paper(env, 2)
    assert progress.summary(env.coord, old)["replaced_by"] == new
    assert progress.summary(env.coord, new)["replaced_by"] is None
    assert progress.summary(env.coord, other)["replaced_by"] is None  # another theorem


def test_a_paper_is_filed_under_the_domain_of_its_main_theorem(env: Env) -> None:
    """The filter on the progress page files each paper once."""
    tickets = [TicketSpec(view("P.u0"), domain="combinatorics"),
               *[TicketSpec(view(f"P.u{i}"), domain="algebra") for i in (1, 2)]]
    sid = env.coord.open_submission(title="P", repo_url="https://x/p", commit="c" * 40,
                                    tickets=tickets, root="P.u0")
    assert progress.summary(env.coord, sid)["domain"] == "combinatorics"
    no_root = env.coord.open_submission(title="Q", repo_url="https://x/q", commit="c" * 40,
                                        tickets=tickets)
    assert progress.summary(env.coord, no_root)["domain"] == "algebra"  # the most frequent


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
                             "domain": "analysis", "state": "error", "discussion": True,
                             "decided_at": env.coord.now().isoformat()}
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


@pytest.mark.req("SR-06")
def test_maintainers_see_the_declaration_as_its_reviewers_do(env: Env) -> None:
    sid = open_paper(env, 2)
    admin, admin_token = env.coord.register("admin", notice_acknowledged=True)
    env.coord.appoint_maintainer(admin)
    _, token = env.coord.register("reader", notice_acknowledged=True)
    client = TestClient(create_app(env.coord, tick_seconds=None))
    query = {"submission_id": sid, "declaration": "P.u0"}
    assert client.get("/api/admin/declaration", params=query).status_code == 401
    reader = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/admin/declaration", params=query, headers=reader).status_code == 403
    maint = {"Authorization": f"Bearer {admin_token}"}
    d = client.get("/api/admin/declaration", params=query, headers=maint).json()
    assert d["view"]["declaration"] == "P.u0" and d["state"] == "not started"
    assert d["paper_passage"]["statement"] == PASSAGE.statement
    assert d["questions"][0]["id"] == "fidelity"
    missing = {"submission_id": sid, "declaration": "P.nope"}
    assert client.get("/api/admin/declaration", params=missing, headers=maint).status_code == 404


DATA = Path(__file__).parent / "data"


def _ingested(tmp_path: Path) -> tuple[Path, AuditLog]:
    """A workdir and an ingest log as the pipeline leaves them."""
    work = tmp_path / "work"
    (work / "analysis").mkdir(parents=True)
    shutil.copy(DATA / "basic" / "core.jsonl", work / "analysis" / "core.jsonl")
    records: list[dict[str, object]] = [{
        "kind": "header", "schema": "dpc.replay/1", "toolchain": "4.33.1", "roots": ["Basic"],
        "trusted": [], "core": "/toolchain/lib/lean", "jobs": 1}]
    for module, origin in {"Init.Core": "core", "Mathlib.Data": "trusted",
                           "Basic": "replayed"}.items():
        records.append({"kind": "module", "module": module, "origin": origin, "entry": "/x",
                        "constants": 7, "skipped": 0, "ok": True, "error": None})
    (work / "analysis" / "replay.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records), "utf-8")
    log = AuditLog(tmp_path / "ingest.sqlite")
    log.append("repo.fetched", {"commit": "c" * 40, "artifact_key": "k", "packages": [
        {"name": "mathlib", "url": "https://github.com/leanprover-community/mathlib4.git",
         "rev": "abc"},
        {"name": "helpers", "url": "https://github.com/someone/helpers", "rev": "def"}]})
    log.append("hardened.snapshot", {"artifact_key": "k", "files": 120})
    log.append("hardened.verified", {"artifact_key": "k", "ok": True})
    return work, log


@pytest.mark.req("SR-42")
def test_what_the_result_relies_on(env: Env, tmp_path: Path) -> None:
    """Proposal C-29: the trusted assumptions, from the ingest's own records."""
    work, log = _ingested(tmp_path)
    fields = trust_basis(work, "c" * 40, log)
    log.close()
    assert fields["toolchain"] == "4.33.1" and fields["axioms"] == ["propext", "Quot.sound"]
    assert (fields["modules_replayed"], fields["constants_replayed"]) == (1, 7)
    assert (fields["modules_trusted"], fields["modules_core"]) == (1, 1)
    assert [lib["name"] for lib in fields["libraries"]] == ["mathlib"]  # official only
    assert fields["hardened_files"] == 120 and fields["hardened_unchanged"] is True
    root = UnitView(declaration="P.u0", decl_kind="theorem", components=(Component(
        target="type", text="∀ x, 0 ≤ Real.sqrt x", glossary=(
            GlossaryEntry(name="Real.sqrt", type="ℝ → ℝ", origin="library"),
            GlossaryEntry(name="P.helper", type="ℝ → ℝ", origin="submission"))),))
    sid = env.coord.open_submission(
        title="P", repo_url="https://x/p", commit="c" * 40, root="P.u0",
        tickets=[TicketSpec(root, domain="analysis"), *specs("P", 2)[1:]])
    env.coord.record_basis(ev.BasisRecorded(submission_id=sid, **fields))
    d = progress.detail(env.coord, sid, None)
    assert d["basis"]["libraries"][0]["rev"] == "abc"
    assert not d["basis"]["libraries_replayed"] and not d["basis"]["second_kernel"]
    assert d["library_definitions"] == [{
        "name": "Real.sqrt", "type": "ℝ → ℝ", "origin": "library", "doc": None,
        "note": "√x = 0 for every x ≤ 0 (Real.sqrt_eq_zero_of_nonpos).",  # today's note
        "used_by": ["P.u0"], "reviewed": False}]


@pytest.mark.req("SR-06")
def test_library_definitions_wait_for_the_planted_errors(tmp_path: Path) -> None:
    """A mutant can use a definition the real statements do not."""
    env = planted_env(tmp_path)
    sid = next(iter(env.coord.state.submissions))
    admin = env.people(1, "admin")[0]
    env.coord.appoint_maintainer(admin)
    assert progress.detail(env.coord, sid, None)["library_definitions"] is None
    assert progress.detail(env.coord, sid, admin)["library_definitions"] == []
    env.log.close()
    env.vault.close()


@pytest.mark.req("SR-06", "SR-21")
def test_whoever_holds_a_planted_copy_unfolds_it_as_the_copy(tmp_path: Path) -> None:
    """C-39: unfolding never shows the original next to one's own planted copy,
    which would reveal the copy before the batch reveal."""
    env = planted_env(tmp_path)
    planted = next(t for t in env.coord.state.tickets.values()
                   if env.vault.is_honeypot(t.ticket_id))
    held: list[str] = []
    for rid in env.people(20):  # someone is offered the planted copy; take it and one other
        cs = env.coord.choice_set(rid)
        if cs is None or planted.ticket_id not in cs.tickets:
            continue
        held.append(env.coord.lease(rid, cs.set_id, planted.ticket_id).lease_id)
        env.coord.return_lease(rid, held[0])  # one version per person, held or not
        nxt = env.coord.choice_set(rid)
        assert nxt is not None
        held.append(env.coord.lease(rid, nxt.set_id, nxt.tickets[0]).lease_id)
        break
    assert len(held) == 2, "the planted copy was never offered"
    other_lease = held[1]
    shown = env.coord.unfold(rid, other_lease, planted.view.declaration)
    assert shown == planted.view  # the copy, as this person saw it
    assert "mutated" in shown.components[0].text
    assert env.events("unit.shown") == []  # nothing new was shown
    env.log.close()
    env.vault.close()
