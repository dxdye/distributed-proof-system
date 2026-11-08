"""Machine-readable system requirements (``requirements/sr.yaml``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = ROOT / "requirements" / "sr.yaml"

REQ_ID = re.compile(r"^SR-\d{2}$")
METHODS = frozenset({"I", "A", "D", "T"})
MILESTONES = ("M0", "M1", "M2", "M3", "M4", "M5", "M6")


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    needs: tuple[int, ...]
    verify: tuple[str, ...]
    milestone: str


def _parse(req_id: str, raw: Any) -> Requirement:
    if not REQ_ID.match(req_id):
        raise ValueError(f"invalid requirement id {req_id!r}")
    if not isinstance(raw, dict):
        raise ValueError(f"{req_id}: expected a mapping")
    methods = tuple(str(m) for m in raw["verify"])
    if not methods or not set(methods) <= METHODS:
        raise ValueError(f"{req_id}: invalid verification methods {methods}")
    milestone = str(raw["milestone"])
    if milestone not in MILESTONES:
        raise ValueError(f"{req_id}: invalid milestone {milestone!r}")
    return Requirement(
        id=req_id,
        text=str(raw["text"]).strip(),
        needs=tuple(int(n) for n in raw["needs"]),
        verify=methods,
        milestone=milestone,
    )


def load_requirements(path: Path = REQUIREMENTS_PATH) -> dict[str, Requirement]:
    """Load and validate the requirement catalogue, ordered by id."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping of requirement ids")
    reqs = {str(k): _parse(str(k), v) for k, v in data.items()}
    return dict(sorted(reqs.items()))
