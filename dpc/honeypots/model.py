"""Output of `dpc-mutate` (JSON Lines, schema ``dpc.mutants/1``)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

SCHEMA = "dpc.mutants/1"


class Mutant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mutant"]
    decl: str
    target: Literal["type", "value", "ctor"]
    component: str = ""  # e.g. the constructor for target "ctor"
    operator: str
    detail: str
    type_correct: bool
    equivalent: bool | None  # None if not type-correct
    equivalent_by: Literal["local", "component"] | None = None
    proof_script: str | None
    auto_detected: Literal["vacuous", "trivial"] | None = None  # §5.2 checks fire
    visible: bool = True  # rendering differs from the original
    original: str
    mutant: str
    mutant_hash: str

    @property
    def usable(self) -> bool:
        """Type-correct, not provably equivalent (SR-07), visible (a change the
        rendering does not show cannot fairly be expected to be found), and not
        already flagged by an automatic check (it would measure the checker)."""
        return (self.type_correct and self.equivalent is False and self.visible
                and self.auto_detected is None)


@dataclass(frozen=True)
class MutantSet:
    toolchain: str
    mutants: tuple[Mutant, ...]

    @classmethod
    def load(cls, path: Path) -> MutantSet:
        lines = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
        if not lines or lines[0].get("schema") != SCHEMA:
            raise ValueError(f"{path}: expected schema {SCHEMA}")
        return cls(str(lines[0]["toolchain"]), tuple(Mutant.model_validate(r) for r in lines[1:]))

    @property
    def usable(self) -> tuple[Mutant, ...]:
        return tuple(m for m in self.mutants if m.usable)

    def stats(self) -> dict[str, object]:
        """Filter rates per operator (verification §11.2: share recognised as equivalent)."""
        total = len(self.mutants)
        return {
            "candidates": total,
            "type_incorrect": sum(not m.type_correct for m in self.mutants),
            "equivalent": sum(m.equivalent is True for m in self.mutants),
            "equivalent_by_component": sum(m.equivalent_by == "component"
                                           for m in self.mutants),
            "auto_detected": sum(m.auto_detected is not None for m in self.mutants),
            "invisible": sum(m.type_correct and m.equivalent is False and not m.visible
                             for m in self.mutants),
            "usable": len(self.usable),
            "by_operator": dict(sorted(Counter(m.operator for m in self.usable).items())),
        }
