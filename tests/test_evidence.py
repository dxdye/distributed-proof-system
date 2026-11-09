"""Evidence check against the fixed commit (SR-10), on lean/fixtures/evidence."""

from __future__ import annotations

import pytest

from dpc.lean.evidence import EvidenceCheck
from dpc.lean.executor import HostExecutor

from conftest import copy_fixture

pytestmark = [pytest.mark.lean, pytest.mark.req("SR-10")]

GOOD = """import Claims

theorem dpc_evidence : ∀ (n : Nat), 3 ≤ n → n < 2 → False := by
  intro n h₁ h₂
  omega
"""

# Provable, but not the vacuity of `Claims.vacuous`.
OTHER_STATEMENT = """import Claims

theorem dpc_evidence : ∀ (n : Nat), n < 0 → False := by
  intro n h
  omega
"""

WITH_SORRY = """import Claims

theorem dpc_evidence : ∀ (n : Nat), 1 ≤ n → False := by
  intro n h
  sorry
"""

WITH_AXIOM = """import Claims

axiom cheat : False

theorem dpc_evidence : ∀ (n : Nat), 1 ≤ n → False := fun _ _ => cheat
"""

# Meta code adds a "proof" without kernel check; only the replay catches it.
FORGED = """import Claims
import Lean

open Lean Elab Term in
set_option debug.skipKernelTC true in
#eval show TermElabM Unit from do
  let type ← elabTerm (← `(∀ (n : Nat), 1 ≤ n → n < 1 → False)) none
  addDecl (.thmDecl { name := `dpc_evidence, levelParams := [], type,
                      value := mkConst ``True.intro })
"""


@pytest.fixture(scope="module")
def check(host_executor: HostExecutor, tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    tmp = tmp_path_factory.mktemp("evidence")
    project = copy_fixture("evidence", tmp)
    assert host_executor.build(project, ["Claims"]).ok
    counter = iter(range(100))

    def run(source: str, target: str = "Claims.vacuous", kind: str = "vacuity") -> EvidenceCheck:
        workdir = tmp / f"check-{next(counter)}"
        return host_executor.check_evidence(project, target=target, kind=kind, source=source,
                                            workdir=workdir)
    return run


def test_exact_vacuity_proof_confirms_the_claim(check) -> None:  # type: ignore[no-untyped-def]
    result = check(GOOD)
    assert result.ok and result.confirms, result
    assert set(result.axioms) <= {"propext", "Classical.choice", "Quot.sound"}


def test_a_different_statement_is_valid_but_does_not_confirm(check) -> None:  # type: ignore[no-untyped-def]
    result = check(OTHER_STATEMENT)
    assert result.ok and not result.confirms and "does not state" in result.reason
    other_kind = check(OTHER_STATEMENT, kind="definition_test_counterexample")
    assert other_kind.ok and not other_kind.confirms and "PVV" in other_kind.reason


@pytest.mark.parametrize(("source", "reason"), [
    (WITH_SORRY, "sorryAx"),
    (WITH_AXIOM, "must not declare axioms"),
    ("import Claims\n\ntheorem dpc_evidence : False := by omega\n", "does not compile"),
    ("import Claims\n\ntheorem other : True := trivial\n", "dpc_evidence"),
])
def test_invalid_evidence_is_rejected(check, source: str, reason: str) -> None:  # type: ignore[no-untyped-def]
    result = check(source)
    assert not result.ok and not result.confirms
    assert reason in result.reason, result


def test_declarations_added_without_kernel_check_are_caught(check) -> None:  # type: ignore[no-untyped-def]
    result = check(FORGED, target="Claims.honest")
    assert not result.ok, result
    assert "rejected by the kernel" in result.reason, result  # lean itself accepted it


def test_honest_statement_has_no_vacuity_proof(check) -> None:  # type: ignore[no-untyped-def]
    # `1 ≤ n → False` is not provable; the best a reviewer can do is fail to compile.
    result = check("import Claims\n\ntheorem dpc_evidence : ∀ (n : Nat), 1 ≤ n → False := by\n"
                   "  intro n h\n  omega\n", target="Claims.honest")
    assert not result.ok and "does not compile" in result.reason
