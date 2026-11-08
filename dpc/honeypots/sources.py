"""Pluggable honeypot sources (docs/adr/0006).

Each source yields usable mutants together with its origin. Today: mutant
files produced by `dpc-mutate` for the campaign's own repository, a foreign
repository or a private pool of non-public formalizations. Further sources
(e.g. informal-side mutations, should the specification be extended) plug in
through the same protocol.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

import numpy as np

from dpc.honeypots.model import Mutant, MutantSet


class Origin(Enum):
    OWN_REPOSITORY = "own_repository"
    FOREIGN_REPOSITORY = "foreign_repository"
    PRIVATE_POOL = "private_pool"


@dataclass(frozen=True)
class Candidate:
    mutant: Mutant
    origin: Origin
    source: str


class HoneypotSource(Protocol):
    name: str

    def candidates(self) -> Sequence[Candidate]: ...


@dataclass(frozen=True)
class MutantFileSource:
    path: Path
    origin: Origin
    name: str = ""

    def candidates(self) -> Sequence[Candidate]:
        label = self.name or self.path.stem
        return [Candidate(m, self.origin, label) for m in MutantSet.load(self.path).usable]


class HoneypotPool:
    """Draws honeypots spread over operators and declarations, so that they do
    not cluster on one kind of error (concept §8.2: spread over difficulty)."""

    def __init__(self, sources: Sequence[HoneypotSource], rng: np.random.Generator) -> None:
        self.rng = rng
        self.by_operator: dict[str, list[Candidate]] = defaultdict(list)
        for source in sources:
            for cand in source.candidates():
                self.by_operator[cand.mutant.operator].append(cand)
        self.used: set[str] = set()

    def __len__(self) -> int:
        return sum(len(v) for v in self.by_operator.values()) - len(self.used)

    def draw(self) -> Candidate:
        """Round-robin over operators (random order), random candidate within."""
        operators = [op for op, cands in self.by_operator.items()
                     if any(c.mutant.mutant_hash not in self.used for c in cands)]
        if not operators:
            raise LookupError("honeypot pool exhausted")
        op = operators[int(self.rng.integers(len(operators)))]
        fresh = [c for c in self.by_operator[op] if c.mutant.mutant_hash not in self.used]
        choice = fresh[int(self.rng.integers(len(fresh)))]
        self.used.add(choice.mutant.mutant_hash)
        return choice
