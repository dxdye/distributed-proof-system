"""Honeypot sources and mixing (offline; SR-06, SR-07)."""

from __future__ import annotations

import json
from dataclasses import asdict
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
    TicketView,
    plan_stream,
)


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
    path = tmp_path / "mutants.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records), "utf-8")
    return path


@pytest.mark.req("SR-07")
def test_only_type_correct_non_equivalent_mutants_are_usable(mutant_file: Path) -> None:
    mutants = MutantSet.load(mutant_file)
    assert len(mutants.mutants) == 22
    assert len(mutants.usable) == 20
    assert mutants.stats()["equivalent"] == 1
    assert mutants.stats()["type_incorrect"] == 1


def test_pool_spreads_over_operators_and_never_repeats(mutant_file: Path) -> None:
    pool = HoneypotPool([MutantFileSource(mutant_file, Origin.PRIVATE_POOL)],
                        np.random.default_rng(0))
    drawn = [pool.draw() for _ in range(20)]
    assert len({c.mutant.mutant_hash for c in drawn}) == 20
    assert {c.mutant.operator for c in drawn[:6]} == {"relation", "constant", "drop_hypothesis"}
    assert all(c.origin is Origin.PRIVATE_POOL for c in drawn)
    with pytest.raises(LookupError):
        pool.draw()


def _real(n: int) -> list[tuple[str, str, tuple[str, ...]]]:
    return [(f"D{i % 5}", f"statement {i}", (f"ctx{i % 5}",)) for i in range(n)]


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
    views = [asdict(s.view) for s in slots]
    assert {tuple(sorted(v)) for v in views} == {tuple(sorted(TicketView.__dataclass_fields__))}
    assert not any("honeypot" in json.dumps(v) for v in views)
    for slot in slots:  # honeypots carry the context of their original declaration
        if slot.is_honeypot:
            assert slot.view.context == (f"ctx{slot.view.declaration[1:]}",)
    ids = [s.view.ticket_id for s in slots]
    assert len(set(ids)) == len(ids)
    positions = [i for i, s in enumerate(slots) if s.is_honeypot]
    assert positions != list(range(len(slots) - len(positions), len(slots)))  # not appended
