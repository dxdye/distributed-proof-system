"""Output of `dpc-replay` (JSON Lines, schema ``dpc.replay/1``, docs/adr/0009).

The kernel replay checks every module of the import closure that is not
loaded from a trusted location (the toolchain or an official package). Each
module record states where it was loaded from (``origin``) and whether all of
its declarations passed the kernel.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dpc.analysis.model import Analysis

SCHEMA = "dpc.replay/1"

Origin = Literal["core", "trusted", "replayed"]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class ReplayHeader(_Record):
    kind: Literal["header"]
    schema_version: str = Field(alias="schema")
    toolchain: str
    roots: tuple[str, ...]
    trusted: tuple[str, ...]  # search path entries trusted besides the toolchain
    core: str  # the toolchain's library
    jobs: int


class ModuleCheck(_Record):
    kind: Literal["module"]
    module: str
    origin: Origin
    entry: str  # search path entry the module was loaded from
    constants: int
    skipped: int  # unsafe and partial constants (safe code cannot use them)
    ok: bool
    error: str | None


@dataclass(frozen=True)
class ReplayReport:
    header: ReplayHeader
    modules: tuple[ModuleCheck, ...]

    @classmethod
    def from_records(cls, records: Iterable[Mapping[str, object]]) -> ReplayReport:
        it = iter(records)
        try:
            header = ReplayHeader.model_validate(next(it))
        except StopIteration:
            raise ValueError("empty replay report") from None
        if header.schema_version != SCHEMA:
            raise ValueError(f"unsupported schema {header.schema_version!r}, expected {SCHEMA!r}")
        modules = tuple(ModuleCheck.model_validate(r) for r in it)
        names = [m.module for m in modules]
        if len(set(names)) != len(names):
            raise ValueError("a module is listed twice")
        return cls(header, modules)

    @classmethod
    def load(cls, path: Path) -> ReplayReport:
        with path.open(encoding="utf-8") as fh:
            return cls.from_records(json.loads(line) for line in fh if line.strip())

    def origin(self, module: str) -> Origin | None:
        return self._origins.get(module)

    @cached_property
    def _origins(self) -> dict[str, Origin]:
        return {m.module: m.origin for m in self.modules}

    @property
    def replayed(self) -> tuple[ModuleCheck, ...]:
        return tuple(m for m in self.modules if m.origin == "replayed")

    @property
    def failures(self) -> tuple[ModuleCheck, ...]:
        """Modules the kernel rejected, and trusted modules importing untrusted ones."""
        return tuple(m for m in self.modules if not m.ok)

    def uncovered(self, analysis: Analysis) -> list[str]:
        """Modules of analysed declarations the replay did not see (should be
        empty: both tools load the same closure)."""
        origins = self._origins
        return sorted({d.module for d in analysis.decls.values()
                       if d.module is not None and d.module not in origins})

    def untrusted_hardened(self, analysis: Analysis) -> list[str]:
        """Modules the analysis counts as hardened (by name) that were loaded from
        an untrusted location. Their declarations would silently drop out of
        TCB_new, so each one is a blocking finding."""
        origins = self._origins
        return sorted({d.module for d in analysis.decls.values()
                       if d.hardened and d.module is not None
                       and origins.get(d.module) == "replayed"})

    def summary(self) -> dict[str, object]:
        """For the audit log: counts and every failure (errors shortened)."""
        replayed = self.replayed
        return {
            "toolchain": self.header.toolchain,
            "roots": list(self.header.roots),
            "modules": len(self.modules),
            "core": sum(m.origin == "core" for m in self.modules),
            "trusted": sum(m.origin == "trusted" for m in self.modules),
            "replayed": len(replayed),
            "constants_replayed": sum(m.constants for m in replayed),
            "skipped_unsafe_or_partial": sum(m.skipped for m in replayed),
            "failures": [{"module": m.module, "error": (m.error or "")[:500]}
                         for m in self.failures],
        }
