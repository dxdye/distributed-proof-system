"""Demo data for trying the web service locally (M4).

The mutation fixture (`lean/fixtures/mutation`, own code, hence trusted) becomes
a submission: its declarations are rendered into ticket views, its mutants are
mixed in as honeypots. Needs a local Lean (elan); no Docker, no network.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from dpc.coord.importer import load_views
from dpc.coord.service import Coordinator, TicketSpec
from dpc.honeypots import HoneypotPool, MutantFileSource, MutantSet, Origin
from dpc.lean.executor import HostExecutor
from dpc.tickets.views import UnitView

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "lean" / "fixtures" / "mutation"
DECLS = ("Mut.pos_le", "Mut.total", "Mut.redundant", "Mut.exists_gt", "Mut.succ_pos'",
         "Mut.double", "Mut.plusZero", "Mut.Bounded", "Mut.window", "Mut.positive")


class DemoError(RuntimeError):
    pass


def seed_demo(coord: Coordinator, workdir: Path, executor: HostExecutor, *,
              share: float = 0.2) -> dict[str, object]:
    project = workdir / "project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(FIXTURE, project, ignore=shutil.ignore_patterns(".lake"))
    if not (result := executor.build(project, ["Mutation"])).ok:
        raise DemoError(result.output)
    views_file, mutants_file = workdir / "views.jsonl", workdir / "mutants.jsonl"
    for out, render in ((views_file, True), (mutants_file, False)):
        result = executor.mutate(project, imports=["Mutation"], decls=list(DECLS), out=out,
                                 render=render)
        if not result.ok:
            raise DemoError(result.output)
    views = load_views(views_file)
    specs = [TicketSpec(UnitView.from_render(views[d]), domain="arithmetic") for d in DECLS]
    pool = HoneypotPool([MutantFileSource(mutants_file, Origin.OWN_REPOSITORY, "fixture")],
                        np.random.default_rng())
    sid = coord.open_submission(title="Mutation fixture (demo)",
                                repo_url="https://example.org/dpc-demo", commit="0" * 40,
                                tickets=specs, pool=pool, share=share)
    return {"submission_id": sid, "units": len(specs),
            "tickets": len(coord.state.submissions[sid].tickets),
            "usable_mutants": len(MutantSet.load(mutants_file).usable)}
