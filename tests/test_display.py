"""Two renderings: with and without the submission's display rules (docs/adr/0011).

A submission can bring notation, coercions and unexpanders that change what a
reviewer sees. Every component is therefore also rendered with the
extensions of the toolchain and the official packages only, by a process that
runs no code of the submission.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dpc.honeypots.mixing import MutantMismatch, honeypot_view
from dpc.honeypots.model import Mutant, MutantSet
from dpc.lean.executor import HostExecutor
from dpc.lean.render import SCHEMA, merge_mutants, merge_views
from dpc.tickets.views import Component, UnitView

from conftest import copy_fixture


def view(text: str, trusted: str | None) -> UnitView:
    return UnitView(declaration="X.claim", decl_kind="theorem",
                    components=(Component(target="type", text=text, trusted_text=trusted),))


def mutant(text: str, trusted: str | None, original: str = "a < b") -> Mutant:
    return Mutant(kind="mutant", decl="X.claim", target="type", operator="relation",
                  detail="", type_correct=True, equivalent=False, proof_script=None,
                  original=original, mutant=text, mutant_hash="1", trusted_mutant=trusted)


# ------------------------------------------------------------- model
def test_a_component_knows_whether_its_display_differs() -> None:
    assert view("a < b", "a ≤ b").components[0].display_differs
    assert not view("a ≤ b", "a ≤ b").components[0].display_differs
    assert not view("a ≤ b", None).components[0].display_differs  # not rendered twice


@pytest.mark.req("SR-06")
def test_honeypots_carry_both_renderings() -> None:
    """A honeypot must look like a real ticket in both renderings."""
    real = view("a < b", "a ≤ b")
    hp = honeypot_view(real, mutant("a < b + 1", "a ≤ b + 1"))
    comp = hp.components[0]
    assert (comp.text, comp.trusted_text) == ("a < b + 1", "a ≤ b + 1")
    assert comp.display_differs
    with pytest.raises(MutantMismatch, match="plain rendering"):
        honeypot_view(real, mutant("a < b + 1", None))
    # Views rendered once only (older data) take mutants either way.
    once = honeypot_view(view("a < b", None), mutant("a < b + 1", "a ≤ b + 1"))
    assert once.components[0].trusted_text is None


def _jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), "utf-8")
    return path


def test_merging_the_second_rendering(tmp_path: Path) -> None:
    views = _jsonl(tmp_path / "views.jsonl", [
        {"kind": "header", "schema": "dpc.mutants/1"},
        {"kind": "view", "decl": "X.claim", "decl_kind": "theorem", "components": [
            {"target": "type", "label": "", "text": "a < b", "glossary": []}]}])
    mutants = _jsonl(tmp_path / "mutants.jsonl", [
        {"kind": "header", "schema": "dpc.mutants/1", "toolchain": "t"},
        {"kind": "mutant", "decl": "X.claim", "target": "type", "component": "",
         "operator": "relation", "detail": "", "type_correct": True, "equivalent": False,
         "proof_script": None, "original": "a < b", "mutant": "a < b + 1",
         "mutant_hash": "7", "expr": ["c", ["X"], []]}])
    trusted = _jsonl(tmp_path / "trusted.jsonl", [
        {"kind": "header", "schema": SCHEMA},
        {"kind": "trusted_view", "decl": "X.claim", "components": [
            {"target": "type", "label": "", "text": "a ≤ b", "glossary": []}]},
        {"kind": "trusted_mutant", "decl": "X.claim", "target": "type", "component": "",
         "mutant_hash": "7", "text": "a ≤ b + 1", "glossary": []}])
    assert merge_views(views, trusted) == {"components": 1, "display_differs": 1, "errors": 0}
    assert merge_mutants(mutants, trusted) == {"mutants": 1}
    record = json.loads(views.read_text("utf-8").splitlines()[1])
    assert UnitView.from_render(record).components[0].display_differs
    assert MutantSet.load(mutants).mutants[0].trusted_mutant == "a ≤ b + 1"


# ------------------------------------------------------------- with Lean
def render_both(executor: HostExecutor, project: Path, root: str, decls: list[str],
                tmp: Path) -> tuple[dict[str, UnitView], MutantSet]:
    views_file, mutants_file = tmp / "views.jsonl", tmp / "mutants.jsonl"
    for out, render in ((views_file, True), (mutants_file, False)):
        assert executor.mutate(project, imports=[root], decls=decls, out=out,
                               render=render).ok
        trusted = out.with_name(out.stem + "-trusted.jsonl")
        result = executor.render_trusted(project, roots=[root], decls=decls if render else [],
                                         mutants=None if render else out, out=trusted)
        assert result.ok, result.output
        (merge_views if render else merge_mutants)(out, trusted)
    views = {}
    for line in views_file.read_text("utf-8").splitlines()[1:]:
        record = json.loads(line)
        if record["kind"] == "view":
            views[record["decl"]] = UnitView.from_render(record)
    return views, MutantSet.load(mutants_file)


@pytest.mark.lean
@pytest.mark.req("SR-06", "SR-20", "SR-21")
def test_a_misleading_display_rule_is_exposed(host_executor: HostExecutor,
                                              tmp_path: Path) -> None:
    """The fixture shows every `a ≤ b` as `a < b`. The plain rendering shows the
    real statement; honest declarations look the same both ways."""
    project = copy_fixture("display", tmp_path)
    assert host_executor.build(project, ["Display"]).ok
    decls = ["Display.claim", "Display.Point", "Display.Point.sum", "Display.double"]
    views, mutants = render_both(host_executor, project, "Display", decls, tmp_path)
    claim = views["Display.claim"].components[0]
    assert claim.text == "∀ (n : Nat), 0 < n → n < n + 1"
    assert claim.trusted_text == "∀ (n : Nat), 0 ≤ n → n ≤ n + 1"
    honest = [c for d in decls[1:] for c in views[d].components]
    assert honest and all(c.trusted_text == c.text for c in honest)
    usable = [m for m in mutants.usable if m.decl == "Display.claim"]
    assert usable and all(m.trusted_mutant for m in usable)
    hp = honeypot_view(views["Display.claim"], usable[0]).components[0]
    assert hp.display_differs and "≤" in (hp.trusted_text or "")


@pytest.mark.lean
@pytest.mark.req("SR-06")
def test_without_own_notation_both_renderings_agree(host_executor: HostExecutor,
                                                    tmp_path: Path) -> None:
    """Both renderings use the same settings: on a project without display
    rules of its own, every component and every mutant looks the same."""
    project = copy_fixture("mutation", tmp_path)
    assert host_executor.build(project, ["Mutation"]).ok
    decls = ["Mut.pos_le", "Mut.double", "Mut.Bounded", "Mut.window", "Mut.positive"]
    views, mutants = render_both(host_executor, project, "Mutation", decls, tmp_path)
    comps = [c for v in views.values() for c in v.components]
    assert comps and all(c.trusted_text == c.text for c in comps)
    usable = mutants.usable
    assert usable and all(m.trusted_mutant == m.mutant for m in usable)
