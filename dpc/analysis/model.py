"""Data model of the analyzer output (interface I-2, JSON Lines).

Mirrors ``lean/analyzer/DpcAnalyzer/Export.lean``. Line 1 is a header record,
all further lines are declaration records.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "dpc.analysis/1"

DeclKind = Literal["axiom", "def", "theorem", "opaque", "quot", "inductive", "ctor", "recursor"]
Mode = Literal["core", "metadata"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Header(_Record):
    kind: Literal["header"]
    schema_version: str = Field(alias="schema")
    mode: Mode
    root: str
    imports: tuple[str, ...]
    toolchain: str
    hardened_prefixes: tuple[str, ...]
    axioms: tuple[str, ...]


class Range(_Record):
    start_line: int
    end_line: int

    @property
    def lines(self) -> int:
        return self.end_line - self.start_line + 1


class Flags(_Record):
    private: bool
    noncomputable: bool
    instance: bool
    unsafe: bool
    partial: bool


class Decl(_Record):
    kind: Literal["decl"]
    name: str
    display_name: str
    decl_kind: DeclKind
    module: str | None
    unit: str
    hardened: bool
    in_tcb: bool
    tcb_deps: tuple[str, ...]
    all_deps: tuple[str, ...] | None
    type_hash: str
    value_hash: str | None
    # Only present in metadata mode:
    range: Range | None = None
    flags: Flags | None = None

    @property
    def is_theorem(self) -> bool:
        return self.decl_kind == "theorem"

    @property
    def meaning_hash(self) -> tuple[str, str | None, str]:
        """Everything that determines the meaning (concept §2.2): proof terms of
        theorems and bodies of opaque constants are excluded."""
        value = None if self.decl_kind in ("theorem", "opaque") else self.value_hash
        return (self.type_hash, value, self.decl_kind)


class SchemaError(ValueError):
    """The analyzer output does not match the expected schema."""


@dataclass(frozen=True)
class Analysis:
    header: Header
    decls: Mapping[str, Decl]

    @classmethod
    def from_records(cls, records: Iterable[Mapping[str, object]]) -> Analysis:
        it = iter(records)
        try:
            first = next(it)
        except StopIteration:
            raise SchemaError("empty analysis") from None
        header = Header.model_validate(first)
        if header.schema_version != SCHEMA_VERSION:
            raise SchemaError(
                f"unsupported schema {header.schema_version!r}, expected {SCHEMA_VERSION!r}"
            )
        decls: dict[str, Decl] = {}
        for raw in it:
            decl = Decl.model_validate(raw)
            if decl.name in decls:
                raise SchemaError(f"duplicate declaration {decl.name}")
            decls[decl.name] = decl
        if header.root not in decls:
            raise SchemaError(f"root {header.root} missing from the declarations")
        return cls(header, decls)

    @classmethod
    def load(cls, path: Path) -> Analysis:
        with path.open(encoding="utf-8") as fh:
            return cls.from_records(json.loads(line) for line in fh if line.strip())

    @property
    def root(self) -> Decl:
        return self.decls[self.header.root]
