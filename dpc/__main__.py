"""Command line interface: ``python -m dpc <command>`` (or ``pixi run dpc <command>``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

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
from dpc.domain.decision import DecisionParams
from dpc.domain.trust import RoleThresholds
from dpc.honeypots import MutantSet
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
            })
            return 0
        executor: LeanExecutor
        if args.executor == "docker":
            executor = DockerExecutor(limits=limits)
        else:
            executor = HostExecutor(trusted=True, cache_dir=Path(args.cache).resolve())
        result = ingest(submission, workdir=workdir, executor=executor, log=log)
        _print(_report(result.analysis) | {"artifact_key": result.artifact_key})
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


def cmd_mutate(args: argparse.Namespace) -> int:
    """Mutants of an ingested submission's class-A units, in its Docker volume (M2)."""
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
    decls = args.decls or [u.name for u in units(Analysis.load(workdir / "analysis" / "core.jsonl"))
                           .values() if u.in_tcb]
    out = workdir / "mutants.jsonl"
    result = ws.mutate(image, manifest, imports=[submission.root_module], decls=decls, out=out)
    if not result.ok:
        print(result.output, file=sys.stderr)
        return 1
    _print(MutantSet.load(out).stats() | {"declarations": decls, "file": str(out)})
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """Agent-based simulation of class-A review (M3)."""
    reviewers = [ReviewerType("honest", args.honest)]
    if args.clickers:
        reviewers.append(ReviewerType("clicker", args.clickers, behaviour="clicker"))
    if args.lookup:
        reviewers.append(ReviewerType("lookup", args.lookup, behaviour="lookup"))
    base = SimConfig(
        items=args.items, error_rate=args.error_rate, blind_share=args.blind_share,
        honeypot_share=args.honeypot_share, reviewers=tuple(reviewers),
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

    p = sub.add_parser("simulate", help="agent-based simulation of class-A review (M3)")
    p.add_argument("--items", type=int, default=300)
    p.add_argument("--error-rate", type=float, default=0.05)
    p.add_argument("--blind-share", type=float, default=0.0, help="ρ, correlated blind spots")
    p.add_argument("--honeypot-share", type=float, default=0.1, help="h")
    p.add_argument("--honest", type=int, default=40)
    p.add_argument("--clickers", type=int, default=0, help="'always correct' reviewers")
    p.add_argument("--lookup", type=int, default=0, help="honeypot lookup attackers")
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
