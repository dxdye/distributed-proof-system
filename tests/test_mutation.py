"""Mutation generator and local equivalence filter on lean/fixtures/mutation (SR-07)."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import copy_fixture
from dpc.honeypots import MutantSet
from dpc.lean.executor import HostExecutor

pytestmark = [pytest.mark.lean, pytest.mark.req("SR-07")]

DECLS = ["Mut.pos_le", "Mut.total", "Mut.redundant", "Mut.exists_gt", "Mut.succ_pos'",
         "Mut.double", "Mut.plusZero"]


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
    }


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
    assert "∃ m, ∀ (n : Nat), n < m" in _texts(mutants, equivalent=False)
    assert {m.target for m in mutants.usable} == {"type", "value"}


def test_stats(mutants: MutantSet) -> None:
    stats = mutants.stats()
    assert stats["candidates"] == len(mutants.mutants)
    assert stats["equivalent"] == 3
    assert stats["usable"] == len(mutants.mutants) - 3


def test_unknown_declaration_fails(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("mutation", tmp_path)
    assert host_executor.build(project, ["Mutation"]).ok
    result = host_executor.mutate(project, imports=["Mutation"], decls=["Mut.nope"],
                                  out=tmp_path / "x.jsonl")
    assert not result.ok
