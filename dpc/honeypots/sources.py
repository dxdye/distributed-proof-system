"""Pluggable honeypot sources (docs/adr/0006).

Each source yields usable mutants together with its origin and whether the
originals are **publicly retrievable**. A honeypot whose original anyone can
look up in a public repository is exposed to the lookup attack (ADR 0006); the
pool can therefore prefer or require non-public sources.

Sources are listed in a registry file (YAML)::

    sources:
      - name: campaign
        path: work/ns/mutants.jsonl
        origin: own_repository
        public: true
      - name: seminar-pool
        path: pools/seminar-2026.jsonl
        origin: private_pool
        public: false

Mutant files are produced by `dpc mutate` (or `dpc-mutate`) on the respective
repository; foreign repositories are ingested like any submission first.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, model_validator

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
    public: bool


class HoneypotSource(Protocol):
    name: str

    def candidates(self) -> Sequence[Candidate]: ...


@dataclass(frozen=True)
class MutantFileSource:
    path: Path
    origin: Origin
    name: str = ""
    public: bool = True

    def candidates(self) -> Sequence[Candidate]:
        label = self.name or self.path.stem
        return [Candidate(m, self.origin, label, self.public)
                for m in MutantSet.load(self.path).usable]


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    path: str
    origin: Origin
    public: bool

    @model_validator(mode="after")
    def _consistent(self) -> SourceSpec:
        if self.origin is Origin.PRIVATE_POOL and self.public:
            raise ValueError(f"source {self.name!r}: a private pool cannot be public")
        return self


def load_registry(path: Path) -> list[MutantFileSource]:
    """Sources from a YAML registry; relative paths are resolved against it."""
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    specs = [SourceSpec.model_validate(s) for s in data.get("sources", [])]
    names = [s.name for s in specs]
    if len(names) != len(set(names)):
        raise ValueError("source names must be unique")
    return [
        MutantFileSource((path.parent / s.path).resolve(), s.origin, s.name, s.public)
        for s in specs
    ]


Policy = Literal["any", "prefer_private", "private_only"]


class HoneypotPool:
    """Draws honeypots spread over operators (concept §8.2: spread over difficulty)
    and, depending on the policy, away from publicly retrievable originals:

    * ``any`` — all usable candidates,
    * ``prefer_private`` — non-public candidates first, public ones only when
      the private supply is exhausted,
    * ``private_only`` — never a candidate whose original is public."""

    def __init__(self, sources: Sequence[HoneypotSource], rng: np.random.Generator,
                 *, policy: Policy = "any") -> None:
        self.rng = rng
        self.policy = policy
        self.candidates: list[Candidate] = [
            cand for source in sources for cand in source.candidates()
            if policy != "private_only" or not cand.public
        ]
        self.used: set[str] = set()

    def __len__(self) -> int:
        return sum(1 for c in self.candidates if c.mutant.mutant_hash not in self.used)

    def composition(self) -> dict[str, int]:
        """Remaining candidates by origin and visibility (for campaign reports)."""
        return dict(sorted(Counter(
            f"{c.origin.value}/{'public' if c.public else 'private'}"
            for c in self.candidates if c.mutant.mutant_hash not in self.used
        ).items()))

    def draw(self, accept: Callable[[Candidate], bool] | None = None) -> Candidate:
        """Draw an unused candidate; ``accept`` restricts the choice (e.g. to
        mutants of declarations that have a ticket in this submission)."""
        fresh = [c for c in self.candidates if c.mutant.mutant_hash not in self.used
                 and (accept is None or accept(c))]
        if not fresh:
            raise LookupError("honeypot pool exhausted")
        if self.policy == "prefer_private" and any(not c.public for c in fresh):
            fresh = [c for c in fresh if not c.public]
        by_operator: dict[str, list[Candidate]] = defaultdict(list)
        for cand in fresh:
            by_operator[cand.mutant.operator].append(cand)
        operators = sorted(by_operator)
        op = operators[int(self.rng.integers(len(operators)))]
        choice = by_operator[op][int(self.rng.integers(len(by_operator[op])))]
        self.used.add(choice.mutant.mutant_hash)
        return choice
