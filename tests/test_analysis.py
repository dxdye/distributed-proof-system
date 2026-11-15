"""Analysis of recorded analyzer output (offline; recorded from lean/fixtures/basic)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dpc.analysis import (
    Analysis,
    AnalysisMismatch,
    SchemaError,
    assign_domains,
    check_axioms,
    classify_axiom,
    merge,
    reverse_degree,
    summarize,
    units,
)

from conftest import DATA

# Hand-checked expectation, see the docstring of lean/fixtures/basic/Basic.lean.
EXPECTED_CLASS_A = {
    "Basic.main_theorem",
    "Basic.isEven",
    "Basic.double",
    "Basic.Point",
    "Basic.instAddPoint",
    "Basic.Color",
    "Basic.Color.toNat",
    "Basic.sumTo",
    "Basic.secret",
    "_private.Basic.0.Basic.offset",
}
EXPECTED_CLASS_B = {"Basic.helper", "Basic.proofOnlyDef"}


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


# ------------------------------------------------------------------- SR-03
@pytest.mark.req("SR-03")
def test_tcb_new_matches_hand_checked_fixture(basic: Analysis) -> None:
    all_units = units(basic)
    assert {u for u, x in all_units.items() if x.in_tcb} == EXPECTED_CLASS_A
    assert {u for u, x in all_units.items() if not x.in_tcb} == EXPECTED_CLASS_B
    assert "Basic.unused" not in basic.decls


@pytest.mark.req("SR-03")
def test_auxiliaries_are_folded_into_their_unit(basic: Analysis) -> None:
    all_units = units(basic)
    assert set(all_units["Basic.Color"].members) >= {
        "Basic.Color", "Basic.Color.red", "Basic.Color.green", "Basic.Color.rec",
        "Basic.Color.casesOn",
    }
    assert set(all_units["Basic.Point"].members) >= {"Basic.Point.mk", "Basic.Point.x"}
    assert "Basic.sumTo.match_1" in all_units["Basic.sumTo"].members
    assert any(m.startswith("Basic.helper._proof") for m in all_units["Basic.helper"].members)


@pytest.mark.req("SR-03")
def test_core_mode_folds_matchers_without_extensions(basic_core: Analysis) -> None:
    assert basic_core.decls["Basic.Color.toNat.match_1"].unit == "Basic.Color.toNat"


@pytest.mark.req("SR-03")
def test_theorem_bodies_and_opaque_values_are_not_in_the_tcb(basic: Analysis) -> None:
    root = basic.root
    assert root.is_theorem
    # The proof mentions helper; the TCB edges of a theorem only follow its type.
    assert "Basic.helper" not in root.tcb_deps
    assert "Basic.helper" in (root.all_deps or ())
    secret = basic.decls["Basic.secret"]
    assert secret.decl_kind == "opaque" and secret.in_tcb


@pytest.mark.req("SR-03")
def test_instances_are_captured_via_types(basic: Analysis) -> None:
    decl = basic.decls["Basic.instAddPoint"]
    assert decl.in_tcb
    assert decl.flags is not None and decl.flags.instance


@pytest.mark.req("SR-03")
def test_summary_counts(basic: Analysis) -> None:
    summary = summarize(basic)
    assert set(summary.tcb_new_units) == EXPECTED_CLASS_A
    assert set(summary.b_new_units) == EXPECTED_CLASS_B
    assert summary.tcb_new_lines == 22
    assert summary.hardened_in_tcb > 0
    assert summary.tcb_decls == summary.tcb_new_decls + summary.hardened_in_tcb
    assert not summary.blocking


def test_reverse_degree(basic: Analysis) -> None:
    degree = reverse_degree(basic)
    assert degree["Basic.main_theorem"] == 0
    # double is used by isEven, helper and (through the proof term) main_theorem.
    assert degree["Basic.double"] == 3


# ------------------------------------------------------------------- SR-02
@pytest.mark.req("SR-02")
@pytest.mark.parametrize(
    ("root", "kind"),
    [("uses_axiom", "custom"), ("sorried", "sorry"), ("native_root", "native")],
)
def test_non_standard_axioms_block(root: str, kind: str) -> None:
    analysis = Analysis.load(DATA / "basic" / "axioms" / f"{root}.jsonl")
    summary = summarize(analysis)
    assert summary.blocking
    assert [f.kind for f in summary.findings] == [kind]


@pytest.mark.req("SR-02")
def test_standard_axioms_do_not_block() -> None:
    analysis = Analysis.load(DATA / "basic" / "axioms" / "standard_root.jsonl")
    assert set(analysis.header.axioms) == {"propext", "Classical.choice", "Quot.sound"}
    assert not summarize(analysis).blocking


@pytest.mark.req("SR-02")
def test_axiom_classification() -> None:
    assert classify_axiom("sorryAx") == "sorry"
    assert classify_axiom("Lean.ofReduceBool") == "native"
    assert classify_axiom("Foo.bar._native.native_decide.ax_1_1") == "native"
    assert classify_axiom("NS.my_axiom") == "custom"
    assert check_axioms(["propext", "Quot.sound"]) == []


# ------------------------------------------------------------ schema, merge
def test_schema_version_is_enforced() -> None:
    records = _records(DATA / "basic" / "core.jsonl")
    records[0]["schema"] = "dpc.analysis/0"
    with pytest.raises(SchemaError):
        Analysis.from_records(records)


def test_unknown_fields_are_rejected() -> None:
    records = _records(DATA / "basic" / "core.jsonl")
    records[1]["surprise"] = 1
    with pytest.raises(ValueError):
        Analysis.from_records(records)


@pytest.mark.req("SR-20")
def test_merge_detects_tampered_metadata(basic_core: Analysis) -> None:
    records = _records(DATA / "basic" / "metadata.jsonl")
    for rec in records[1:]:
        if rec["name"] == "Basic.double":
            rec["in_tcb"] = False  # a hostile initializer hides a definition
    with pytest.raises(AnalysisMismatch, match="in_tcb"):
        merge(basic_core, Analysis.from_records(records))


@pytest.mark.req("SR-20")
def test_merge_detects_dropped_declarations(basic_core: Analysis) -> None:
    records = [r for r in _records(DATA / "basic" / "metadata.jsonl")
               if r.get("name") != "Basic.secret"]
    with pytest.raises(AnalysisMismatch, match="declaration sets"):
        merge(basic_core, Analysis.from_records(records))


def test_merge_rejects_units_pointing_into_hardened_code(basic_core: Analysis) -> None:
    records = _records(DATA / "basic" / "metadata.jsonl")
    for rec in records[1:]:
        if rec["name"] == "Basic.double":
            rec["unit"] = "Nat"
    merged = merge(basic_core, Analysis.from_records(records))
    assert merged.decls["Basic.double"].unit == "Basic.double"


# ------------------------------------------------------------------- SR-04
@pytest.mark.req("SR-04")
def test_domains_from_library_modules_and_overrides(basic: Analysis) -> None:
    # Pretend Nat lived in Mathlib's number theory: everything built on it inherits.
    decls = dict(basic.decls)
    decls["Nat"] = decls["Nat"].model_copy(update={"module": "Mathlib.NumberTheory.Basic"})
    analysis = Analysis(basic.header, decls)
    domains = assign_domains(analysis, overrides={"Basic.Color": "combinatorics"})
    assert domains["Basic.double"].domain == "number_theory"
    assert domains["Basic.double"].source == "library"
    assert domains["Basic.Color"].source == "override"
    assert set(domains) == EXPECTED_CLASS_A


@pytest.mark.req("SR-04")
def test_a_repository_sorting_its_modules_by_area_is_believed(basic: Analysis) -> None:
    """openai/math files its papers as OAI.Combinatorics.*, OAI.NumberTheory.*:
    the authors' classification beats the Mathlib vocabulary a statement uses."""
    decls = dict(basic.decls)
    decls["Nat"] = decls["Nat"].model_copy(update={"module": "Mathlib.Algebra.Basic"})
    for name, d in basic.decls.items():
        if d.module == "Basic":
            decls[name] = d.model_copy(update={"module": "OAI.NumberTheory.Jacobsthal.Basic"})
    domains = assign_domains(Analysis(basic.header, decls))
    assert domains["Basic.double"].domain == "number_theory"
    assert domains["Basic.double"].source == "module"
    assert all(d.domain == "number_theory" for d in domains.values())


@pytest.mark.req("SR-04")
def test_domains_unassigned_without_evidence(basic: Analysis) -> None:
    domains = assign_domains(basic)
    assert all(d.source == "unassigned" for d in domains.values())
