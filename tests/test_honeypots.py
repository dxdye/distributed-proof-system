"""Honeypot sources and mixing (offline; SR-06, SR-07)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dpc.honeypots import (
    MAX_SHARE,
    SCHEMA,
    HoneypotPool,
    MutantFileSource,
    MutantSet,
    Origin,
    SourceSpec,
    honeypot_view,
    load_registry,
    plan_stream,
)
from dpc.honeypots.mixing import MutantMismatch
from dpc.honeypots.model import Mutant
from dpc.tickets.views import Component, GlossaryEntry, UnitView


def _mutant(decl: str, op: str, text: str, *, equivalent: bool | None = False,
            type_correct: bool = True) -> dict[str, object]:
    return {"kind": "mutant", "decl": decl, "target": "type", "operator": op, "detail": "",
            "type_correct": type_correct, "equivalent": equivalent, "proof_script": None,
            "original": f"orig {decl}", "mutant": text, "mutant_hash": f"{decl}:{text}"}


@pytest.fixture
def mutant_file(tmp_path: Path) -> Path:
    records = [{"kind": "header", "schema": SCHEMA, "toolchain": "4.33.1"}]
    for i in range(20):
        records.append(_mutant(f"D{i % 5}", ["relation", "constant", "drop_hypothesis"][i % 3],
                               f"mutant {i}"))
    records.append(_mutant("D9", "relation", "equivalent one", equivalent=True))
    records.append(_mutant("D9", "relation", "ill-typed", equivalent=None, type_correct=False))
    records.append(_mutant("D9", "constant", "orig D9", ) | {"visible": False})
    path = tmp_path / "mutants.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    return path


@pytest.mark.req("SR-07")
def test_only_type_correct_non_equivalent_visible_mutants_are_usable(mutant_file: Path) -> None:
    mutants = MutantSet.load(mutant_file)
    assert len(mutants.mutants) == 23
    assert len(mutants.usable) == 20
    stats = mutants.stats()
    assert (stats["equivalent"], stats["type_incorrect"], stats["invisible"]) == (1, 1, 1)


def test_pool_spreads_over_operators_and_never_repeats(mutant_file: Path) -> None:
    pool = HoneypotPool([MutantFileSource(mutant_file, Origin.PRIVATE_POOL)],
                        np.random.default_rng(0))
    drawn = [pool.draw() for _ in range(20)]
    assert len({c.mutant.mutant_hash for c in drawn}) == 20
    assert {c.mutant.operator for c in drawn[:6]} == {"relation", "constant", "drop_hypothesis"}
    assert all(c.origin is Origin.PRIVATE_POOL for c in drawn)
    with pytest.raises(LookupError):
        pool.draw()


def _view(decl: str, ctx: tuple[str, ...] = ()) -> UnitView:
    return UnitView(declaration=decl, decl_kind="def", context=ctx, components=(
        Component(target="type", text=f"orig {decl}",
                  glossary=(GlossaryEntry(name="Nat", type="Type"),)),
        Component(target="value", text=f"body of {decl}"),
    ))


def _real(n: int) -> list[UnitView]:
    """``n`` real units; D0..D4 have mutants in the fixture file."""
    return [_view(f"D{i}" if i < 5 else f"U{i}", (f"ctx{i}",)) for i in range(n)]


@pytest.mark.req("SR-06")
@pytest.mark.parametrize("share", [0.0, 0.05, 0.1, 0.2])
def test_honeypot_share_is_configurable_up_to_twenty_percent(mutant_file: Path,
                                                             share: float) -> None:
    pool = HoneypotPool([MutantFileSource(mutant_file, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(1))
    slots = plan_stream(_real(80), pool, np.random.default_rng(2), share=share)
    honeypots = sum(s.is_honeypot for s in slots)
    assert honeypots / len(slots) == pytest.approx(share, abs=0.01)


@pytest.mark.req("SR-06")
def test_share_above_limit_is_rejected(mutant_file: Path) -> None:
    pool = HoneypotPool([MutantFileSource(mutant_file, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(1))
    with pytest.raises(ValueError, match="SR-06"):
        plan_stream(_real(10), pool, np.random.default_rng(0), share=MAX_SHARE + 0.01)


@pytest.mark.req("SR-06")
def test_views_do_not_reveal_honeypots(mutant_file: Path) -> None:
    pool = HoneypotPool([MutantFileSource(mutant_file, Origin.OWN_REPOSITORY)],
                        np.random.default_rng(1))
    slots = plan_stream(_real(40), pool, np.random.default_rng(3), share=0.2)
    assert sum(s.is_honeypot for s in slots) == 10
    shapes = {(len(s.view.components), tuple(c.target for c in s.view.components))
              for s in slots}
    assert len(shapes) == 1  # same components for real tickets and honeypots
    assert not any("honeypot" in s.view.model_dump_json() for s in slots)
    for slot in slots:  # honeypots carry the context of their original declaration
        if slot.is_honeypot:
            assert slot.view.context == (f"ctx{slot.view.declaration[1:]}",)
            assert slot.view.components[0].text.startswith("mutant")
            assert slot.view.components[1].text == f"body of {slot.view.declaration}"
    positions = [i for i, s in enumerate(slots) if s.is_honeypot]
    assert positions != list(range(len(slots) - len(positions), len(slots)))  # not appended


@pytest.mark.req("SR-06")
def test_honeypot_view_replaces_exactly_the_mutated_component() -> None:
    mutant = Mutant.model_validate(_mutant("D1", "relation", "mutant x") | {
        "glossary": [{"name": "LE.le", "type": "α → α → Prop"}]})
    view = honeypot_view(_view("D1"), mutant)
    assert view.components[0].text == "mutant x"
    assert [g.name for g in view.components[0].glossary] == ["LE.le"]  # rendered for the mutant
    assert view.components[1] == _view("D1").components[1]
    with pytest.raises(MutantMismatch, match="rendering"):  # formatting would give it away
        honeypot_view(_view("D1").model_copy(update={"components": (
            Component(target="type", text="orig  D1"),)}), mutant)
    with pytest.raises(MutantMismatch):
        honeypot_view(_view("D2"), mutant)


def test_pool_short_of_fitting_mutants_mixes_in_fewer() -> None:
    from dpc.honeypots.mixing import honeypot_count

    assert honeypot_count(90, 0.1) == 10
    pool = HoneypotPool([], np.random.default_rng(0))
    slots = plan_stream(_real(20), pool, np.random.default_rng(0), share=0.2)
    assert not any(s.is_honeypot for s in slots) and len(slots) == 20


# ------------------------------------------------- registry and policies (ADR 0006)
def _registry(tmp_path: Path, mutant_file: Path) -> Path:
    private = tmp_path / "private.jsonl"
    lines = mutant_file.read_text("utf-8").splitlines()
    private.write_text("\n".join([lines[0]] + [
        line.replace('"mutant_hash": "', '"mutant_hash": "private:') for line in lines[1:6]
    ]), "utf-8")
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        "sources:\n"
        f"  - {{name: campaign, path: {mutant_file.name}, origin: own_repository, public: true}}\n"
        "  - {name: seminar, path: private.jsonl, origin: private_pool, public: false}\n",
        "utf-8")
    return registry


def test_registry_loads_sources_with_origin_and_visibility(tmp_path: Path,
                                                         mutant_file: Path) -> None:
    sources = load_registry(_registry(tmp_path, mutant_file))
    assert [(s.name, s.origin, s.public) for s in sources] == [
        ("campaign", Origin.OWN_REPOSITORY, True), ("seminar", Origin.PRIVATE_POOL, False)]
    pool = HoneypotPool(sources, np.random.default_rng(0))
    assert pool.composition() == {"own_repository/public": 20, "private_pool/private": 5}


def test_private_pool_cannot_be_public() -> None:
    with pytest.raises(ValueError, match="private pool"):
        SourceSpec(name="x", path="p", origin=Origin.PRIVATE_POOL, public=True)


@pytest.mark.parametrize("policy", ["prefer_private", "private_only"])
def test_policies_avoid_publicly_retrievable_originals(tmp_path: Path, mutant_file: Path,
                                                      policy: str) -> None:
    sources = load_registry(_registry(tmp_path, mutant_file))
    pool = HoneypotPool(sources, np.random.default_rng(1), policy=policy)  # type: ignore[arg-type]
    first = [pool.draw() for _ in range(5)]
    assert all(not c.public for c in first)  # private supply is used first
    if policy == "private_only":
        with pytest.raises(LookupError):
            pool.draw()
    else:
        assert pool.draw().public  # then it falls back to public candidates
