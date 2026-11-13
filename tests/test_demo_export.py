"""Click dummy snapshot (dpc export-demo): derived from the implementation, and
planted errors only from own fixtures (a public dummy burns its honeypots)."""

from __future__ import annotations

import json
from pathlib import Path

from dpc.demo_export import SCHEMA, Source, export


def _write(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), "utf-8")
    return path


def _view(decl: str, text: str) -> dict[str, object]:
    return {"kind": "view", "decl": decl, "decl_kind": "theorem", "components": [
        {"target": "type", "label": "", "text": text, "glossary": []}]}


def test_snapshot_plants_errors_only_from_fixtures(tmp_path: Path) -> None:
    head = {"kind": "header", "schema": "dpc.mutants/1", "toolchain": "t"}
    fixture_views = _write(tmp_path / "fx-views.jsonl", [head, _view("F.a", "0 < n"),
                                                          _view("F.b", "1 ≤ n")])
    fixture_mutants = _write(tmp_path / "fx-mutants.jsonl", [head, {
        "kind": "mutant", "decl": "F.a", "target": "type", "operator": "relation",
        "detail": "", "type_correct": True, "equivalent": False, "proof_script": None,
        "original": "0 < n", "mutant": "0 ≤ n", "mutant_hash": "1"}])
    real_views = _write(tmp_path / "real-views.jsonl", [head, _view("R.main", "∀ s, P s")])
    out = tmp_path / "snapshot.json"
    counts = export([
        Source("fx", "Fixture", "https://example.org/fx", "0" * 40, "arithmetic",
               fixture_views, mutants=fixture_mutants, honeypots=1),
        Source("real", "Real", "https://example.org/real", "1" * 40, "analysis", real_views),
    ], out)
    snap = json.loads(out.read_text("utf-8"))
    assert snap["schema"] == SCHEMA and counts == {"tickets": 4, "honeypots": 1}
    assert snap["questions"]["definition"][0]["id"] == "fidelity"
    assert "Nothing is proven" in snap["purpose"]["definition"]
    fx, real = snap["submissions"]
    planted = [t for t in fx["tickets"] if t["honeypot"]]
    assert len(planted) == 1 and planted[0]["view"]["components"][0]["text"] == "0 ≤ n"
    assert all(t["honeypot"] is None for t in real["tickets"])
    assert all(t["tier"] in ("easy", "medium", "hard", "excellence")
               for s in snap["submissions"] for t in s["tickets"])
