"""Command line interface: ``python -m dpc <command>`` (or ``pixi run dpc <command>``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from dpc.analysis import (
    Analysis,
    assign_domains,
    graph_diff,
    merge,
    reverse_degree,
    summarize,
    units,
)
from dpc.audit import AuditLog
from dpc.coord import BlobStore, Coordinator, CoordParams, Vault
from dpc.coord.importer import load_views, ticket_specs
from dpc.domain.decision import DecisionParams
from dpc.domain.trust import RoleThresholds
from dpc.honeypots import HoneypotPool, MutantFileSource, MutantSet, Origin, load_registry
from dpc.ingest import Submission, ingest
from dpc.ingest.volume import ingest_in_volume, volume_name
from dpc.lean.executor import DockerExecutor, HostExecutor, LeanExecutor, Limits
from dpc.lean.project import Manifest
from dpc.lean.workspace import VolumeWorkspace
from dpc.requirements import load_requirements
from dpc.sim import ReviewerType, SimConfig, simulate
from dpc.sim.study import Grid, render_markdown, run_study

DEFAULT_CACHE = Path(".dpc-cache")


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _report(analysis: Analysis) -> dict[str, object]:
    summary = summarize(analysis)
    degree = reverse_degree(analysis)
    domains = assign_domains(analysis)
    return {
        **summary.as_dict(),
        "blocking": summary.blocking,
        "class_a_units": {u: {"deg_minus": degree[u], "domain": domains[u].domain}
                          for u in summary.tcb_new_units},
        "class_b_units": {u: {"deg_minus": degree[u]} for u in summary.b_new_units},
    }


def cmd_analyze_local(args: argparse.Namespace) -> int:
    """Build and analyse a *trusted* local project (fixtures, development)."""
    project = Path(args.project).resolve()
    executor = HostExecutor(trusted=True, cache_dir=Path(args.cache).resolve())
    imports = args.imports or [args.root.split(".")[0]]
    build = executor.build(project, imports)
    if not build.ok:
        print(build.output, file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir).resolve()
    paths = {}
    for mode in ("core", "metadata"):
        paths[mode] = out_dir / f"{mode}.jsonl"
        result = executor.analyze(project, root=args.root, imports=imports, mode=mode,
                                  out=paths[mode])
        if not result.ok:
            print(result.output, file=sys.stderr)
            return 1
    analysis = merge(Analysis.load(paths["core"]), Analysis.load(paths["metadata"]))
    _print(_report(analysis))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    submission = Submission.model_validate_json(Path(args.submission).read_text("utf-8"))
    limits = Limits(cpus=args.cpus, memory=args.memory, timeout_s=args.timeout_h * 3600)
    workdir = Path(args.workdir).resolve()
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    with AuditLog(args.log) as log:
        if args.executor == "docker-volume":
            vol = ingest_in_volume(submission, executor=DockerExecutor(limits=limits), log=log,
                                   out_dir=workdir / "analysis")
            _print(_report(vol.analysis) | {
                "artifact_key": vol.artifact_key, "volume": vol.volume,
                "unverified_hardened_modules": list(vol.unverified_hardened),
                "kernel_replay": vol.replay.summary(), "blocking": vol.blocking,
            })
            return 0
        executor: LeanExecutor
        if args.executor == "docker":
            executor = DockerExecutor(limits=limits)
        else:
            executor = HostExecutor(trusted=True, cache_dir=Path(args.cache).resolve())
        result = ingest(submission, workdir=workdir, executor=executor, log=log)
        _print(_report(result.analysis) | {
            "artifact_key": result.artifact_key,
            "unverified_hardened_modules": list(result.untrusted_hardened),
            "kernel_replay": result.replay.summary(), "blocking": result.blocking,
        })
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    _print(_report(Analysis.load(Path(args.file))))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    _print(graph_diff(Analysis.load(Path(args.old)), Analysis.load(Path(args.new))).as_dict())
    return 0


def cmd_audit_verify(args: argparse.Namespace) -> int:
    with AuditLog(args.log) as log:
        result = log.verify(expected_head=args.head)
    _print(result.__dict__)
    return 0 if result.ok else 1


def _class_a_names(workdir: Path) -> list[str]:
    return [u.name for u in units(Analysis.load(workdir / "analysis" / "core.jsonl")).values()
            if u.in_tcb]


def _run_in_volume(args: argparse.Namespace, *, render: bool, out: Path) -> int:
    """`dpc-mutate` in the submission's Docker volume (untrusted step)."""
    submission = Submission.model_validate_json(Path(args.submission).read_text("utf-8"))
    workdir = Path(args.workdir).resolve()
    executor = DockerExecutor(limits=Limits(cpus=args.cpus, memory=args.memory,
                                            timeout_s=args.timeout_h * 3600))
    ws = VolumeWorkspace(executor, volume_name(submission), submission.project_dir)
    fetch_image = ws.ensure_fetch_image()
    toolchain = ws.read_text(ws.project / "lean-toolchain", fetch_image).strip()
    manifest = Manifest.model_validate_json(
        ws.read_text(ws.project / "lake-manifest.json", fetch_image))
    image = executor.ensure_image(toolchain)
    decls = args.decls or _class_a_names(workdir)
    result = ws.mutate(image, manifest, imports=[submission.root_module], decls=decls,
                       out=out, render=render)
    if not result.ok:
        print(result.output, file=sys.stderr)
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """Ticket views (components + glossary) of the class-A units (M4, SR-21)."""
    out = Path(args.workdir).resolve() / "views.jsonl"
    if (code := _run_in_volume(args, render=True, out=out)) != 0:
        return code
    _print({"views": len(load_views(out)), "file": str(out)})
    return 0


def _coordinator(args: argparse.Namespace) -> Coordinator:
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    log = AuditLog(Path(args.log) if args.log else data / "audit.sqlite")
    params = CoordParams.from_overrides(json.loads(Path(args.params).read_text("utf-8"))) \
        if getattr(args, "params", None) else None
    return Coordinator(log, Vault(data / "vault.sqlite"), params,
                       blobs=BlobStore(data / "blobs"))


def cmd_demo(args: argparse.Namespace) -> int:
    """Seed a local demo: the mutation fixture as a submission, one maintainer."""
    from dpc.coord.demo import seed_demo

    coord = _coordinator(args)
    executor = HostExecutor(trusted=True, cache_dir=Path(args.cache).resolve())
    info = seed_demo(coord, Path(args.data).resolve() / "demo-work", executor,
                     share=args.share)
    _, token = coord.register(args.maintainer, "expert", notice_acknowledged=True)
    rid = coord.vault.reviewer_for_pseudonym(args.maintainer)
    assert rid is not None
    coord.appoint_maintainer(rid)
    _print(info | {"maintainer": args.maintainer, "maintainer_token": token})
    return 0


def cmd_open_submission(args: argparse.Namespace) -> int:
    """Open an ingested, rendered submission for review (SR-05, SR-06)."""
    submission = Submission.model_validate_json(Path(args.submission).read_text("utf-8"))
    workdir = Path(args.workdir).resolve()
    core = workdir / "analysis" / "core.jsonl"
    metadata = workdir / "analysis" / "metadata.jsonl"
    analysis = Analysis.load(core)
    if metadata.exists():
        analysis = merge(analysis, Analysis.load(metadata))
    specs = ticket_specs(analysis, submission.commit, load_views(workdir / "views.jsonl"))
    coord = _coordinator(args)
    rng = np.random.default_rng()
    pool = None
    if args.registry:
        pool = HoneypotPool(load_registry(Path(args.registry)), rng, policy=args.policy)
    elif (workdir / "mutants.jsonl").exists():
        own = MutantFileSource(workdir / "mutants.jsonl", Origin.OWN_REPOSITORY, "own", True)
        pool = HoneypotPool([own], rng, policy=args.policy)
    authors = [rid for name in args.authors or []
               if (rid := coord.vault.reviewer_for_pseudonym(name)) is not None]
    sid = coord.open_submission(
        title=args.title or submission.root, repo_url=submission.repo_url,
        commit=submission.commit, tickets=specs, pool=pool, share=args.share, lab=args.lab,
        authors=authors)
    _print({"submission_id": sid, "units": len(specs),
            "tickets": len(coord.state.submissions[sid].tickets)})
    return 0


def cmd_appoint(args: argparse.Namespace) -> int:
    coord = _coordinator(args)
    rid = coord.vault.reviewer_for_pseudonym(args.pseudonym)
    if rid is None:
        print(f"unknown pseudonym {args.pseudonym!r}", file=sys.stderr)
        return 1
    coord.appoint_maintainer(rid)
    _print({"maintainer": args.pseudonym, "reviewer_id": rid})
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from dpc.api import create_app

    coord = _coordinator(args)
    web = Path(args.web) if args.web else None
    uvicorn.run(create_app(coord, static_dir=web, tick_seconds=args.tick),
                host=args.host, port=args.port)
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    """Mutants of an ingested submission's class-A units, in its Docker volume (M2)."""
    out = Path(args.workdir).resolve() / "mutants.jsonl"
    if (code := _run_in_volume(args, render=False, out=out)) != 0:
        return code
    _print(MutantSet.load(out).stats() | {"file": str(out)})
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """Agent-based simulation of class-A review (M3)."""
    reviewers = [ReviewerType("honest", args.honest)]
    if args.clickers:
        reviewers.append(ReviewerType("clicker", args.clickers, behaviour="clicker"))
    if args.lookup:
        reviewers.append(ReviewerType("lookup", args.lookup, behaviour="lookup"))
    if args.sybils:
        reviewers.append(ReviewerType("sybil", args.sybils, behaviour="sybil"))
    if args.colluders:
        reviewers.append(ReviewerType("colluder", args.colluders, behaviour="colluder"))
    base = SimConfig(
        items=args.items, error_rate=args.error_rate, blind_share=args.blind_share,
        honeypot_share=args.honeypot_share, reviewers=tuple(reviewers),
        detection_model="irt" if args.irt else "beta",
        honeypot_difficulty_shift=args.honeypot_shift, lenses=args.lenses, delphi=args.delphi,
        target_share=args.target_share, pair_window=args.pair_window,
        decision=DecisionParams(prior_error=args.error_rate, delta_a=args.delta_a,
                                k_min=args.k_min, max_rounds=args.max_rounds),
        roles=RoleThresholds(theta_pv=args.theta_pv, theta_pvv=args.theta_pvv),
    )
    seeds = range(args.seed, args.seed + args.runs)
    runs = [simulate(replace(base, seed=s)).as_dict() for s in seeds]
    _print(runs[0] if len(runs) == 1 else runs)
    return 0


def cmd_study(args: argparse.Namespace) -> int:
    """Parameter study (M3) rendered as Markdown."""
    grid = Grid(items=args.items, seeds=tuple(range(args.seeds)))
    text = render_markdown(run_study(grid), grid)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_requirements(_: argparse.Namespace) -> int:
    reqs = load_requirements()
    _print({"total": len(reqs),
            "by_milestone": dict(sorted(Counter(r.milestone for r in reqs.values()).items()))})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dpc", description="Distributed Proof Check")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze-local", help="build + analyse a trusted local Lake project")
    p.add_argument("project")
    p.add_argument("--root", required=True, help="fully qualified main theorem")
    p.add_argument("--import", dest="imports", action="append", help="module(s) to import")
    p.add_argument("--out-dir", default="build/analysis")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.set_defaults(func=cmd_analyze_local)

    p = sub.add_parser("ingest", help="ingest a submission (I-1 JSON)")
    p.add_argument("submission")
    p.add_argument("--workdir", required=True)
    p.add_argument("--log", default="data/audit.sqlite")
    p.add_argument("--executor", choices=["docker", "docker-volume", "host-trusted"],
                   default="docker",
                   help="docker-volume: workspace in a Docker volume, with Mathlib cache")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    p.add_argument("--cpus", type=float, default=Limits.cpus)
    p.add_argument("--memory", default=Limits.memory)
    p.add_argument("--timeout-h", type=float, default=Limits.timeout_s / 3600)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("summary", help="summarise an analysis file")
    p.add_argument("file")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("diff", help="graph diff between two analyses (SR-16)")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("audit-verify", help="verify the audit log hash chain")
    p.add_argument("log")
    p.add_argument("--head", help="expected head hash (detects truncation)")
    p.set_defaults(func=cmd_audit_verify)

    p = sub.add_parser("mutate", help="honeypot mutants of an ingested submission (M2)")
    p.add_argument("submission")
    p.add_argument("--workdir", required=True, help="workdir of the earlier ingest")
    p.add_argument("--decl", dest="decls", action="append",
                   help="declarations (default: all class-A units)")
    p.add_argument("--cpus", type=float, default=Limits.cpus)
    p.add_argument("--memory", default=Limits.memory)
    p.add_argument("--timeout-h", type=float, default=Limits.timeout_s / 3600)
    p.set_defaults(func=cmd_mutate)

    p = sub.add_parser("render", help="ticket views of an ingested submission (M4)")
    p.add_argument("submission")
    p.add_argument("--workdir", required=True, help="workdir of the earlier ingest")
    p.add_argument("--decl", dest="decls", action="append",
                   help="declarations (default: all class-A units)")
    p.add_argument("--cpus", type=float, default=Limits.cpus)
    p.add_argument("--memory", default=Limits.memory)
    p.add_argument("--timeout-h", type=float, default=1.0)
    p.set_defaults(func=cmd_render)

    def coord_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data", default="data/coord", help="audit log, vault and blobs")
        p.add_argument("--log", help="audit log (default: <data>/audit.sqlite)")
        p.add_argument("--params", help="JSON file with parameter overrides (CoordParams)")

    p = sub.add_parser("open-submission", help="create the class-A tickets (M4)")
    p.add_argument("submission")
    p.add_argument("--workdir", required=True, help="with analysis/, views.jsonl, mutants")
    p.add_argument("--title")
    p.add_argument("--share", type=float, default=None, help="honeypot share h (SR-06)")
    p.add_argument("--registry", help="honeypot source registry (ADR 0006)")
    p.add_argument("--policy", choices=["any", "prefer_private", "private_only"],
                   default="any")
    p.add_argument("--lab", help="submitting lab (SR-50)")
    p.add_argument("--author", dest="authors", action="append", help="author pseudonym")
    coord_args(p)
    p.set_defaults(func=cmd_open_submission)

    p = sub.add_parser("appoint", help="appoint a maintainer")
    p.add_argument("pseudonym")
    coord_args(p)
    p.set_defaults(func=cmd_appoint)

    p = sub.add_parser("demo", help="seed a local demo from the mutation fixture (M4)")
    p.add_argument("--share", type=float, default=0.2, help="honeypot share h")
    p.add_argument("--maintainer", default="maintainer", help="pseudonym of the maintainer")
    p.add_argument("--cache", default=str(DEFAULT_CACHE))
    coord_args(p)
    p.set_defaults(func=cmd_demo, data="data/demo")

    p = sub.add_parser("serve", help="run the web service (M4)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--web", default="web/dist", help="built frontend to serve")
    p.add_argument("--tick", type=float, default=60.0, help="seconds between ticks")
    coord_args(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("simulate", help="agent-based simulation of class-A review (M3)")
    p.add_argument("--items", type=int, default=300)
    p.add_argument("--error-rate", type=float, default=0.05)
    p.add_argument("--blind-share", type=float, default=0.0, help="ρ, correlated blind spots")
    p.add_argument("--honeypot-share", type=float, default=0.1, help="h")
    p.add_argument("--honest", type=int, default=40)
    p.add_argument("--clickers", type=int, default=0, help="'always correct' reviewers")
    p.add_argument("--lookup", type=int, default=0, help="honeypot lookup attackers")
    p.add_argument("--sybils", type=int, default=0, help="accounts of one Sybil attacker")
    p.add_argument("--colluders", type=int, default=0, help="colluding PV/PVV accounts")
    p.add_argument("--target-share", type=float, default=0.0,
                   help="share of erroneous items the attackers want accepted")
    p.add_argument("--pair-window", type=int, default=0, help="SR-08 pair repetition window")
    p.add_argument("--lenses", action="store_true", help="assign lenses greedily (§8.4)")
    p.add_argument("--delphi", action="store_true", help="Delphi round 2 (§8.6)")
    p.add_argument("--irt", action="store_true", help="IRT detection model (§8.2)")
    p.add_argument("--honeypot-shift", type=float, default=0.0,
                   help="honeypot difficulty relative to real errors (< 0: easier)")
    p.add_argument("--delta-a", type=float, default=1e-3)
    p.add_argument("--k-min", type=int, default=3)
    p.add_argument("--max-rounds", type=int, default=4)
    p.add_argument("--theta-pv", type=float, default=0.45)
    p.add_argument("--theta-pvv", type=float, default=0.7)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--runs", type=int, default=1, help="replications with consecutive seeds")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("study", help="parameter study of the review process (M3)")
    p.add_argument("--items", type=int, default=300)
    p.add_argument("--seeds", type=int, default=2)
    p.add_argument("--out", default="docs/simulation/parameter-study.md")
    p.set_defaults(func=cmd_study)

    p = sub.add_parser("requirements", help="requirement catalogue statistics")
    p.set_defaults(func=cmd_requirements)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
