"""Static difficulty estimate for tickets (concept §8.1; SR-33).

Static features from the analysis: number of direct dependencies, depth in
the TCB (distance from the main theorem), source lines, instances among the
dependencies, noncomputable definitions. They are standardised within the
campaign and combined with provisional weights into a difficulty ``b``.
Empirical features (abort rate, processing time, disagreement) and the IRT
calibration of the weights follow in the pilot (concept §8.2).
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass

from dpc.analysis.model import Analysis
from dpc.analysis.tcb import Unit

#: Provisional weights (to be calibrated with IRT on pilot data).
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "deps": 0.4,
    "depth": 0.1,
    "lines": 0.3,
    "instances": 0.1,
    "noncomputable": 0.1,
}


@dataclass(frozen=True)
class StaticFeatures:
    deps: int
    depth: int
    lines: int
    instances: int
    noncomputable: int

    def as_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in DEFAULT_WEIGHTS}


def _depths(analysis: Analysis) -> dict[str, int]:
    """Distance of every declaration from the root along TCB edges."""
    depth = {analysis.header.root: 0}
    todo = deque([analysis.header.root])
    while todo:
        name = todo.popleft()
        decl = analysis.decls.get(name)
        if decl is None:
            continue
        for dep in decl.tcb_deps:
            if dep not in depth and dep in analysis.decls:
                depth[dep] = depth[name] + 1
                todo.append(dep)
    return depth


def static_features(analysis: Analysis, units: Mapping[str, Unit]) -> dict[str, StaticFeatures]:
    depth = _depths(analysis)
    out: dict[str, StaticFeatures] = {}
    for name, unit in units.items():
        members = [analysis.decls[m] for m in unit.members]
        deps = {d for m in members for d in m.tcb_deps} - set(unit.members)
        instances = sum(1 for d in deps if (x := analysis.decls.get(d)) is not None
                        and x.flags is not None and x.flags.instance)
        noncomputable = sum(1 for m in members if m.flags is not None and m.flags.noncomputable)
        out[name] = StaticFeatures(
            deps=len(deps),
            depth=min((depth.get(m, 0) for m in unit.members), default=0),
            lines=unit.lines or 0,
            instances=instances,
            noncomputable=noncomputable,
        )
    return out


def static_difficulty(
    features: Mapping[str, StaticFeatures], weights: Mapping[str, float] = DEFAULT_WEIGHTS
) -> dict[str, float]:
    """Weighted sum of features standardised (z-scores of log1p) over the campaign."""
    if not features:
        return {}
    names = list(features)
    columns = {k: [math.log1p(features[n].as_dict()[k]) for n in names] for k in weights}
    scores = dict.fromkeys(names, 0.0)
    for key, values in columns.items():
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) or 1.0
        for name, value in zip(names, values, strict=True):
            scores[name] += weights[key] * (value - mean) / sd
    return {n: round(s, 3) for n, s in scores.items()}
