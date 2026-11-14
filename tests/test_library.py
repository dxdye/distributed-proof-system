"""What a statement takes from Mathlib, in every ticket (proposal C-27)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import register

from dpc.api import create_app
from dpc.coord import TicketSpec
from dpc.tickets.library import relies_on
from dpc.tickets.questions import TEXTS, questions_for
from dpc.tickets.views import Component, GlossaryEntry, UnitView

from test_coord import Env, params


def lib(name: str, origin: str = "library", note: str | None = None) -> GlossaryEntry:
    return GlossaryEntry(name=name, type="…", origin=origin, note=note)


ZETA = UnitView(declaration="OAI.zeta", decl_kind="theorem", components=(Component(
    target="type", text="∀ {s : ℂ}, 7 / 8 < s.re → riemannZeta s ≠ 0",
    glossary=(lib("Complex"), lib("Complex.re"), lib("HDiv.hDiv", "core"),
              lib("LT.lt", "core"), lib("Nat", "core"), lib("Ne", "core"),
              lib("OfNat.ofNat", "core"), lib("riemannZeta"), lib("OAI.helper", "submission"))),))


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


@pytest.mark.req("SR-21")
def test_a_ticket_lists_what_its_statement_takes_from_mathlib() -> None:
    """Without notation plumbing; conventions to know first, with the note
    of today even if the view was rendered before the note existed."""
    names = [g.name for g in relies_on(ZETA)]
    assert names == ["riemannZeta", "Complex", "Complex.re", "Nat"]
    zeta = relies_on(ZETA)[0]
    assert zeta.note is not None and "riemannZeta_one" in zeta.note


@pytest.mark.req("SR-21")
def test_the_plain_rendering_decides_what_is_listed() -> None:
    """The submission's notation can make a constant look like another
    (ADR 0011): the list comes from the plain rendering where there is one."""
    view = UnitView(declaration="P.t", decl_kind="theorem", components=(Component(
        target="type", text="∀ x, P.good x", glossary=(lib("P.good", "submission"),),
        trusted_text="∀ x, 0 < Real.sqrt x", trusted_glossary=(lib("Real.sqrt"),)),))
    assert [g.name for g in relies_on(view)] == ["Real.sqrt"]


@pytest.mark.req("SR-21")
def test_the_junk_value_question_names_them() -> None:
    plain = {q["id"]: q["text"] for q in questions_for("theorem")}
    here = {q["id"]: q["text"] for q in questions_for("theorem", relies_on(ZETA))}
    assert plain == TEXTS["theorem"]
    assert here["junk_values"].startswith(TEXTS["theorem"]["junk_values"])
    assert "relies on riemannZeta, Complex, Complex.re, Nat" in here["junk_values"]
    assert "Conventions to know are noted for riemannZeta." in here["junk_values"]
    assert {k: v for k, v in here.items() if k != "junk_values"} == \
        {k: v for k, v in plain.items() if k != "junk_values"}
    many = tuple(lib(f"Lib.c{i}") for i in range(9))
    assert "Lib.c5 and 3 more" in questions_for("definition", many)[1]["text"]


@pytest.mark.req("SR-21", "SR-06")
def test_the_lease_shows_the_list_and_the_question(env: Env) -> None:
    env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                              tickets=[TicketSpec(ZETA, domain="number theory")])
    client = TestClient(create_app(env.coord, tick_seconds=None))
    auth = register(client, "carol")
    cs = client.post("/api/choice-set", headers=auth).json()
    lease = client.post("/api/leases", headers=auth, json={
        "set_id": cs["set_id"], "ticket_id": cs["tickets"][0]["ticket_id"]}).json()
    ticket = lease["ticket"]
    assert [g["name"] for g in ticket["relies_on"]] == ["riemannZeta", "Complex", "Complex.re",
                                                       "Nat"]
    assert "riemannZeta" in ticket["questions"][1]["text"]
    hover = {g["name"]: g for g in ticket["view"]["components"][0]["glossary"]}
    assert hover["riemannZeta"]["note"] == ticket["relies_on"][0]["note"]  # the same note
