"""Paper passages on class-A tickets (SR-24, concept OS-3)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dpc.api import create_app
from dpc.coord import Conflict, CoordError, TicketSpec
from dpc.honeypots import HoneypotPool, MutantFileSource, Origin
from dpc.tickets.paper import PaperMap

from test_coord import Env, params, view

PAPER = r"""
mapped_by: maintainer-anna
source:
  title: "On a zero-free region"
  arxiv: "2411.01234"
  version: "v2"
  url: "https://arxiv.org/abs/2411.01234v2"
units:
  P.u0:
    locator: "Theorem 1.1, p. 2"
    statement: |
      For every $s \in \mathbb{C}$ with $\operatorname{Re} s > 7/8$, $\zeta(s) \neq 0$.
    domain: number theory
"""


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params(honeypot_share=0.2))
    yield e
    e.log.close()
    e.vault.close()


def paper(tmp_path: Path) -> PaperMap:
    path = tmp_path / "paper.yaml"
    path.write_text(PAPER, "utf-8")
    return PaperMap.load(path)


def test_paper_map_gives_passages_and_domain_corrections(tmp_path: Path) -> None:
    m = paper(tmp_path)
    passage = m.passage("P.u0")
    assert passage is not None and passage.locator == "Theorem 1.1, p. 2"
    assert passage.statement.startswith("For every $s") and passage.mapped_by == "maintainer-anna"
    assert m.domain("P.u0") == "number theory"
    assert m.passage("P.u1") is None and m.domain("P.u1") is None


@pytest.mark.req("SR-06", "SR-24")
def test_honeypots_show_the_paper_passage_of_their_original(env: Env, tmp_path: Path) -> None:
    """The paper says what the original claims; a honeypot that differs from it
    is detectable only next to the passage, so both carry the same one."""
    m = paper(tmp_path)
    mutants = tmp_path / "mutants.jsonl"
    records = [{"kind": "header", "schema": "dpc.mutants/1", "toolchain": "x"}] + [
        {"kind": "mutant", "decl": "P.u0", "target": "type", "operator": "constant",
         "detail": "", "type_correct": True, "equivalent": False, "proof_script": None,
         "original": "statement of P.u0", "mutant": f"mutated {i}", "mutant_hash": str(i)}
        for i in range(4)]
    mutants.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    pool = HoneypotPool([MutantFileSource(mutants, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(0))
    specs = [TicketSpec(view(f"P.u{i}"), domain="analysis", paper=m.passage(f"P.u{i}"))
             for i in range(4)]
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=specs, pool=pool, paper_ref="arXiv:2411.01234")
    of_u0 = [t for t in env.coord.state.tickets.values() if t.view.declaration == "P.u0"]
    assert len(of_u0) == 2  # the real ticket and its honeypot
    assert of_u0[0].paper == of_u0[1].paper == m.passage("P.u0")
    others = [t for t in env.coord.state.tickets.values() if t.view.declaration != "P.u0"]
    assert all(t.paper is None for t in others)  # not mapped: shown as such


@pytest.mark.req("SR-24")
def test_reviewers_can_contest_the_mapping(env: Env, tmp_path: Path) -> None:
    m = paper(tmp_path)
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40, tickets=[
        TicketSpec(view("P.u0"), domain="number theory", paper=m.passage("P.u0"))])
    client = TestClient(create_app(env.coord, tick_seconds=None))
    token = client.post("/api/register", json={"pseudonym": "rita",
                                               "notice_acknowledged": True}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    cs = client.post("/api/choice-set", headers=auth).json()
    lease = client.post("/api/leases", headers=auth, json={
        "set_id": cs["set_id"], "ticket_id": cs["tickets"][0]["ticket_id"]}).json()
    assert lease["ticket"]["paper_passage"]["locator"] == "Theorem 1.1, p. 2"
    assert lease["ticket"]["domain"] == "number theory"
    lid = lease["lease_id"]
    short = client.post(f"/api/leases/{lid}/contest-mapping", headers=auth, json={"reason": "no"})
    assert short.status_code == 400
    ok = client.post(f"/api/leases/{lid}/contest-mapping", headers=auth,
                     json={"reason": "Theorem 1.1 is about Re s > 1; 7/8 is Theorem 3.2"})
    assert ok.status_code == 200
    assert client.get(f"/api/leases/{lid}", headers=auth).json()[
        "ticket"]["mapping_contested_by_me"] is True
    with pytest.raises(Conflict):
        env.coord.contest_mapping(env.coord.vault.reviewer_for_pseudonym("rita") or "", lid,
                                  "the same complaint once more, long enough")
    admin = env.people(1, "admin")[0]
    env.coord.appoint_admin(admin)
    contested = [t for t in env.coord.state.tickets.values() if t.contests]
    assert contested and contested[0].contests[0][1].startswith("Theorem 1.1 is about")


def test_tickets_without_a_passage_cannot_be_contested(env: Env) -> None:
    env.coord.open_submission(title="P", repo_url="https://x", commit="c" * 40,
                              tickets=[TicketSpec(view("P.u0"), domain="analysis")])
    rid = env.people(1)[0]
    lid = env.take(rid)
    with pytest.raises(CoordError, match="no paper passage"):
        env.coord.contest_mapping(rid, lid, "there is no passage, so nothing to contest")


@pytest.mark.req("SR-24")
def test_the_main_theorem_needs_its_passage_before_review(tmp_path: Path) -> None:
    """C-39: without a common passage the votes do not answer the same question."""
    from dpc.tickets.paper import require_main_passage

    with pytest.raises(ValueError, match="no paper passage"):
        require_main_passage(None, "P.main")
    paper_file = tmp_path / "paper.yaml"
    paper_file.write_text(
        "source: {title: On P, url: https://arxiv.org/abs/0000.00000}\n"
        "mapped_by: maintainer\n"
        "units:\n"
        "  P.helper: {locator: Lemma 2, statement: Something.}\n", "utf-8")
    paper = PaperMap.load(paper_file)
    with pytest.raises(ValueError, match=r"P.main"):
        require_main_passage(paper, "P.main")
    require_main_passage(paper, "P.helper")
