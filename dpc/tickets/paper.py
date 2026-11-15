"""Where a class-A declaration comes from in the paper (SR-24, concept OS-3).

A reviewer can only judge fidelity next to the informal statement. For every
class-A declaration a maintainer records the passage of the paper: the
source (arXiv id and version), where it is (theorem number, page) and the
statement itself, with LaTeX math between ``$`` signs. The mapping must not
come from the model or system that generated the proof (SR-24); reviewers can
contest it.

A pilot reads the mapping from a YAML file per submission (``dpc
open-submission --paper FILE``). A dedicated mapping ticket before class A
can replace the file later. Example::

    mapped_by: maintainer-pseudonym
    source:
      title: "On the zeros of ..."
      arxiv: "2411.01234"
      version: "v2"
      url: "https://arxiv.org/abs/2411.01234v2"
    units:
      OAI.main_theorem:
        locator: "Theorem 1.1, p. 2"
        statement: |
          For every $s \\in \\mathbb{C}$ with $\\operatorname{Re} s > 7/8$, $\\zeta(s) \\neq 0$.
        domain: number theory     # optional correction of the domain (SR-04)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PaperSource(_Model):
    title: str
    arxiv: str | None = None
    version: str | None = None
    url: str | None = None


class PaperPassage(_Model):
    """What a ticket shows as "the paper says"."""

    source: PaperSource
    locator: str = Field(min_length=1)  # e.g. "Theorem 1.1, p. 2"
    statement: str = Field(min_length=1)  # informal statement, LaTeX math in $…$
    mapped_by: str = Field(min_length=1)  # a person, never the generating model (SR-24)
    note: str = ""


class PaperUnit(_Model):
    locator: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    domain: str | None = None  # correction of the automatic domain (SR-04)
    note: str = ""


class PaperMap(_Model):
    mapped_by: str = Field(min_length=1)
    source: PaperSource
    units: dict[str, PaperUnit] = {}

    @classmethod
    def load(cls, path: Path) -> PaperMap:
        return cls.model_validate(yaml.safe_load(path.read_text("utf-8")))

    def passage(self, declaration: str) -> PaperPassage | None:
        unit = self.units.get(declaration)
        if unit is None:
            return None
        return PaperPassage(source=self.source, locator=unit.locator,
                            statement=unit.statement.strip(), mapped_by=self.mapped_by,
                            note=unit.note)

    def domain(self, declaration: str) -> str | None:
        unit = self.units.get(declaration)
        return unit.domain if unit else None


def require_main_passage(paper: PaperMap | None, root: str) -> None:
    """The main theorem must have its paper passage before review starts
    (concept §16 step 3, SR-24, ADR 0012, C-39): without a common passage every
    reviewer compares with another place, and the k_min votes do not answer the
    same question. Other class-A declarations may follow later."""
    if paper is None or paper.passage(root) is None:
        raise ValueError(f"the main theorem {root} has no paper passage: map it in the paper "
                         "file (paper.yaml) before opening the submission")
