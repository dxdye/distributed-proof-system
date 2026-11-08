"""Graph diff on synthetic modifications of the recorded fixture (offline)."""

from __future__ import annotations

import pytest

from dpc.analysis import Analysis, graph_diff, units

pytestmark = pytest.mark.req("SR-16")


def _modify(analysis: Analysis, name: str, **changes: object) -> Analysis:
    decls = dict(analysis.decls)
    decls[name] = decls[name].model_copy(update=changes)
    return Analysis(analysis.header, decls)


def _class_a(analysis: Analysis) -> set[str]:
    return {u for u, x in units(analysis).items() if x.in_tcb}


def test_identical_commits_invalidate_nothing(basic: Analysis) -> None:
    diff = graph_diff(basic, basic)
    assert not diff.invalidated_units
    assert diff.kept_units == set(units(basic))


def test_changed_definition_invalidates_exactly_its_dependents(basic: Analysis) -> None:
    new = _modify(basic, "Basic.double", value_hash="changed")
    diff = graph_diff(basic, new)
    assert diff.meaning_changed == {"Basic.double"}
    # isEven unfolds to double, main_theorem states isEven, helper's statement uses double.
    assert diff.invalidated_units == {
        "Basic.double", "Basic.isEven", "Basic.main_theorem", "Basic.helper",
    }
    assert "Basic.Point" in diff.kept_units


def test_proof_change_invalidates_no_class_a_ticket(basic: Analysis) -> None:
    new = _modify(basic, "Basic.main_theorem", proof_hash="another-proof")
    diff = graph_diff(basic, new)
    assert diff.proof_only_changed == {"Basic.main_theorem"}
    assert not diff.meaning_changed
    assert not diff.invalidated_units & _class_a(basic)


def test_opaque_body_change_is_not_a_meaning_change(basic: Analysis) -> None:
    new = _modify(basic, "Basic.secret", proof_hash="other-witness")
    assert not graph_diff(basic, new).invalidated_units


def test_change_in_constructor_invalidates_the_inductive(basic: Analysis) -> None:
    new = _modify(basic, "Basic.Color.green", type_hash="changed")
    diff = graph_diff(basic, new)
    assert {"Basic.Color", "Basic.Color.toNat", "Basic.main_theorem"} <= diff.invalidated_units
    assert "Basic.Point" not in diff.invalidated_units


def test_unit_moving_from_class_b_to_a_is_invalidated(basic: Analysis) -> None:
    new = _modify(basic, "Basic.helper", in_tcb=True)
    assert "Basic.helper" in graph_diff(basic, new).invalidated_units
