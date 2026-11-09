"""Mutation generator and local equivalence filter on lean/fixtures/mutation (SR-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dpc.honeypots import MutantSet
from dpc.lean.executor import HostExecutor

from conftest import copy_fixture

pytestmark = [pytest.mark.lean, pytest.mark.req("SR-07")]

DECLS = ["Mut.pos_le", "Mut.total", "Mut.redundant", "Mut.exists_gt", "Mut.succ_pos'",
         "Mut.double", "Mut.plusZero", "Mut.Bounded", "Mut.window", "Mut.positive"]


@pytest.fixture(scope="module")
def mutants(host_executor: HostExecutor, tmp_path_factory: pytest.TempPathFactory) -> MutantSet:
    tmp = tmp_path_factory.mktemp("mutation")
    project = copy_fixture("mutation", tmp)
    assert host_executor.build(project, ["Mutation"]).ok
    out = tmp / "mutants.jsonl"
    result = host_executor.mutate(project, imports=["Mutation"], decls=DECLS, out=out)
    assert result.ok, result.output
    return MutantSet.load(out)


def _texts(mutants: MutantSet, *, equivalent: bool) -> set[str]:
    return {m.mutant for m in mutants.mutants if m.equivalent is equivalent}


def test_every_candidate_type_checks(mutants: MutantSet) -> None:
    assert mutants.mutants
    assert all(m.type_correct for m in mutants.mutants)


def test_meaning_preserving_changes_are_discarded(mutants: MutantSet) -> None:
    assert _texts(mutants, equivalent=True) == {
        "∀ (n : Nat), 1 < n → 2 ≤ n",  # dropped h₂ follows from h₁
        "∀ (n : Nat), 1 < n → 0 ≤ n → 2 ≤ n",  # 0 < n ↔ 0 ≤ n given 1 < n
        "∀ (n : Nat), 0 ≤ n + 1",  # 0 < n + 1 ↔ 0 ≤ n + 1
        "fun (n : Nat) => 0 ≤ n ∧ 1 ≤ n",  # equivalent as a whole body (component)
        "fun (n : Nat) => 0 < n ∧ 0 ≤ n",  # idem
    }


def test_component_equivalence_for_definitions(mutants: MutantSet) -> None:
    """Locally `0 < n ↔ 0 ≤ n` fails, but the whole body is equivalent because
    of the other conjunct — meaningful for definitions, not for theorems."""
    by_component = {m.mutant for m in mutants.mutants if m.equivalent_by == "component"}
    assert by_component == {"fun (n : Nat) => 0 ≤ n ∧ 1 ≤ n", "fun (n : Nat) => 0 < n ∧ 0 ≤ n"}
    assert "fun (n : Nat) => 0 < n ∧ 1 < n" in _texts(mutants, equivalent=False)


def test_automatically_detectable_mutants_are_not_usable(mutants: MutantSet) -> None:
    """Contradictory hypotheses are found by the vacuity check of concept §5.2;
    such a honeypot would measure the checker, not the reviewer."""
    vacuous = {m.mutant for m in mutants.mutants if m.auto_detected == "vacuous"}
    assert vacuous == {
        "∀ (n : Nat), 3 ≤ n → n < 3 → n = 3",
        "∀ (n : Nat), 2 < n → n < 3 → n = 2",
        "∀ (n : Nat), 2 ≤ n → n < 2 → n = 2",
    }
    assert not any(m.usable for m in mutants.mutants if m.auto_detected)
    # pos_le is trivially provable itself, so trivial mutants of it are not flagged
    assert not any(m.auto_detected for m in mutants.mutants if m.decl == "Mut.pos_le")


def test_true_but_different_claims_are_kept(mutants: MutantSet) -> None:
    """A whole-statement filter (M ↔ D) would discard these: D is proven, so
    M ↔ D holds for every true M. They are exactly the subtle honeypots we want
    (docs/adr/0007)."""
    kept = _texts(mutants, equivalent=False)
    assert "∀ (n : Nat), 1 < n → 1 ≤ n" in kept  # stronger hypothesis, still true
    assert "∀ (n : Nat), 0 < n → 0 ≤ n" in kept  # trivialised conclusion


def test_all_operators_are_exercised(mutants: MutantSet) -> None:
    operators = {m.operator for m in mutants.usable}
    assert operators >= {"relation", "constant", "drop_hypothesis", "swap_quantifiers"}
    assert "∃ (m : Nat), ∀ (n : Nat), n < m" in _texts(mutants, equivalent=False)
    assert {m.target for m in mutants.usable} == {"type", "value", "ctor"}


def test_structure_fields_are_mutated(mutants: MutantSet) -> None:
    """The meaning of a structure lives in its constructor's fields."""
    fields = {m.mutant for m in mutants.usable if m.decl == "Mut.Bounded"}
    assert "∀ {f : Nat → Nat}, (∀ (n : Nat), f n < 10) → Mut.Bounded f" in fields
    assert "∀ {f : Nat → Nat}, Mut.Bounded f" in fields  # condition dropped
    assert {m.component for m in mutants.usable if m.decl == "Mut.Bounded"} == {"Mut.Bounded.mk"}


def test_binder_types_are_rendered(mutants: MutantSet) -> None:
    """Changes inside binder types (e.g. ℝ³ → ℝ⁴) must be visible to reviewers."""
    assert "fun (n : Nat) => 3 * n" in _texts(mutants, equivalent=False)
    assert all(m.visible for m in mutants.mutants)


def test_stats(mutants: MutantSet) -> None:
    stats = mutants.stats()
    assert stats["candidates"] == len(mutants.mutants)
    assert stats["equivalent"] == 5
    assert stats["auto_detected"] == 3
    assert stats["usable"] == len(mutants.mutants) - 5 - 3


def test_unknown_declaration_fails(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("mutation", tmp_path)
    assert host_executor.build(project, ["Mutation"]).ok
    result = host_executor.mutate(project, imports=["Mutation"], decls=["Mut.nope"],
                                  out=tmp_path / "x.jsonl")
    assert not result.ok


# ------------------------------------------------------ ticket views (M4, SR-21)
@pytest.fixture(scope="module")
def views(host_executor: HostExecutor, tmp_path_factory: pytest.TempPathFactory
          ) -> dict[str, dict[str, object]]:
    tmp = tmp_path_factory.mktemp("render")
    project = copy_fixture("mutation", tmp)
    assert host_executor.build(project, ["Mutation"]).ok
    out = tmp / "views.jsonl"
    result = host_executor.mutate(project, imports=["Mutation"], decls=DECLS, out=out,
                                  render=True)
    assert result.ok, result.output
    lines = [json.loads(line) for line in out.read_text("utf-8").splitlines() if line]
    return {r["decl"]: r for r in lines[1:]}


@pytest.mark.req("SR-21", "SR-06")
def test_views_have_the_components_a_mutant_can_replace(
        views: dict[str, dict[str, object]], mutants: MutantSet) -> None:
    from dpc.honeypots import honeypot_view
    from dpc.tickets.views import UnitView

    unit = {name: UnitView.from_render(record) for name, record in views.items()}
    assert [c.target for c in unit["Mut.pos_le"].components] == ["type"]
    assert [c.target for c in unit["Mut.positive"].components] == ["type", "value"]
    assert [(c.target, c.label) for c in unit["Mut.Bounded"].components][1] == \
        ("ctor", "Mut.Bounded.mk")
    usable = mutants.usable
    assert usable
    for m in usable:  # same rendering: every usable mutant fits its view
        honeypot_view(unit[m.decl], m)
        assert m.glossary or m.target == "value"


@pytest.mark.req("SR-21")
def test_glossary_lists_used_constants_with_types(views: dict[str, dict[str, object]]) -> None:
    from dpc.tickets.views import UnitView

    window = UnitView.from_render(views["Mut.window"])
    names = {g.name for c in window.components for g in c.glossary}
    assert "Nat" in names and "Mut.window" not in names
    assert not any(n.startswith("inst") for n in names)  # instances are left out
