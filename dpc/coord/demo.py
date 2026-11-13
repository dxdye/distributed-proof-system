"""Demo data for trying the web service locally (M4).

Own fixtures (hence trusted) become submissions: their declarations are
rendered into ticket views, twice (with and without the submission's display
rules, docs/adr/0011), and their mutants are mixed in as honeypots.

* ``lean/fixtures/mutation``: ordinary arithmetic declarations.
* ``lean/fixtures/display``: a submission whose own display rule prints every
  ``a ≤ b`` as ``a < b``; its tickets show both renderings.

Needs a local Lean (elan); no Docker, no network.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dpc.coord.importer import load_views
from dpc.coord.service import Coordinator, TicketSpec
from dpc.honeypots import HoneypotPool, MutantFileSource, MutantSet, Origin
from dpc.lean.executor import HostExecutor
from dpc.lean.render import merge_mutants, merge_views
from dpc.tickets.views import UnitView

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "lean" / "fixtures"


@dataclass(frozen=True)
class DemoSubmission:
    fixture: str
    root: str
    title: str
    domain: str
    decls: tuple[str, ...]


MUTATION = DemoSubmission(
    "mutation", "Mutation", "Mutation fixture (demo)", "arithmetic",
    ("Mut.pos_le", "Mut.total", "Mut.redundant", "Mut.exists_gt", "Mut.succ_pos'",
     "Mut.double", "Mut.plusZero", "Mut.Bounded", "Mut.window", "Mut.positive"))
DISPLAY = DemoSubmission(
    "display", "Display", "Display rules fixture (demo)", "arithmetic",
    ("Display.claim", "Display.Point", "Display.Point.sum", "Display.double",
     "Display.sum_comm"))
DECLS = MUTATION.decls  # kept for callers of the single-submission demo


class DemoError(RuntimeError):
    pass


def _render(executor: HostExecutor, project: Path, demo: DemoSubmission,
            workdir: Path) -> tuple[Path, Path]:
    views_file, mutants_file = workdir / "views.jsonl", workdir / "mutants.jsonl"
    decls = list(demo.decls)
    for out, render in ((views_file, True), (mutants_file, False)):
        result = executor.mutate(project, imports=[demo.root], decls=decls, out=out,
                                 render=render)
        if not result.ok:
            raise DemoError(result.output)
        # Second rendering without the submission's display rules (ADR 0011).
        trusted = out.with_name(out.stem + "-trusted.jsonl")
        result = executor.render_trusted(project, roots=[demo.root],
                                         decls=decls if render else [],
                                         mutants=None if render else out, out=trusted)
        if not result.ok:
            raise DemoError(result.output)
        (merge_views if render else merge_mutants)(out, trusted)
    return views_file, mutants_file


def seed_submission(coord: Coordinator, workdir: Path, executor: HostExecutor,
                    demo: DemoSubmission, *, share: float) -> dict[str, object]:
    workdir.mkdir(parents=True, exist_ok=True)
    project = workdir / "project"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(FIXTURES / demo.fixture, project, ignore=shutil.ignore_patterns(".lake"))
    if not (result := executor.build(project, [demo.root])).ok:
        raise DemoError(result.output)
    views_file, mutants_file = _render(executor, project, demo, workdir)
    views = load_views(views_file)
    specs = [TicketSpec(UnitView.from_render(views[d]), domain=demo.domain)
             for d in demo.decls]
    pool = HoneypotPool([MutantFileSource(mutants_file, Origin.OWN_REPOSITORY, demo.fixture)],
                        np.random.default_rng())
    sid = coord.open_submission(title=demo.title, repo_url=f"https://example.org/{demo.fixture}",
                                commit="0" * 40, tickets=specs, pool=pool, share=share)
    return {"submission_id": sid, "units": len(specs),
            "tickets": len(coord.state.submissions[sid].tickets),
            "usable_mutants": len(MutantSet.load(mutants_file).usable)}


def seed_demo(coord: Coordinator, workdir: Path, executor: HostExecutor, *,
              share: float = 0.2,
              submissions: tuple[DemoSubmission, ...] = (MUTATION,)) -> dict[str, object]:
    """Open the given fixtures as submissions. With one submission, the result
    describes it directly; with several, per fixture under ``submissions``."""
    infos = {demo.fixture: seed_submission(coord, workdir / demo.fixture, executor, demo,
                                           share=share)
             for demo in submissions}
    if len(infos) == 1:
        return next(iter(infos.values()))
    return {"submissions": infos}
