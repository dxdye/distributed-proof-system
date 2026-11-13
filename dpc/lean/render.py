"""Second rendering without the submission's display rules (docs/adr/0011).

``dpc-mutate`` renders views and mutants with the submission's environment
extensions; ``dpc-render`` renders the same components with the extensions of
the toolchain and the official packages only. This module merges the second
rendering into the files of the first:

* view records: every component gets ``trusted_text`` and ``trusted_glossary``;
* mutant records: every mutant with an encoded expression gets
  ``trusted_mutant`` and ``trusted_glossary``.

The files are rewritten in place, so everything downstream reads one file.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = "dpc.trusted-render/1"


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8", newline="\n")


def _trusted(path: Path) -> list[dict[str, Any]]:
    records = _records(path)
    if not records or records[0].get("schema") != SCHEMA:
        raise ValueError(f"{path}: not an output of dpc-render")
    return records[1:]


def merge_views(views: Path, trusted: Path) -> dict[str, int]:
    """Add the trusted rendering to every view component. Returns counts."""
    by_decl = {r["decl"]: r for r in _trusted(trusted) if r.get("kind") == "trusted_view"}
    errors = sum(r.get("kind") == "error" for r in _trusted(trusted))
    records = _records(views)
    merged = differs = 0
    for record in records:
        if record.get("kind") != "view" or record["decl"] not in by_decl:
            continue
        plain = {(c["target"], c["label"]): c for c in by_decl[record["decl"]]["components"]}
        for comp in record["components"]:
            other = plain.get((comp["target"], comp["label"]))
            if other is None:
                continue
            comp["trusted_text"] = other["text"]
            comp["trusted_glossary"] = other["glossary"]
            merged += 1
            differs += other["text"] != comp["text"]
    _write(views, records)
    return {"components": merged, "display_differs": differs, "errors": errors}


def mutant_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(record["decl"]), str(record["target"]), str(record.get("component", "")),
            str(record["mutant_hash"]))


def merge_mutants(mutants: Path, trusted: Path) -> dict[str, int]:
    """Add the trusted rendering to every mutant that has one. Returns counts."""
    by_key = {mutant_key(r): r for r in _trusted(trusted) if r.get("kind") == "trusted_mutant"}
    records = _records(mutants)
    merged = 0
    for record in records:
        if record.get("kind") != "mutant":
            continue
        other = by_key.get(mutant_key(record))
        if other is not None:
            record["trusted_mutant"] = other["text"]
            record["trusted_glossary"] = other["glossary"]
            merged += 1
    _write(mutants, records)
    return {"mutants": merged}
