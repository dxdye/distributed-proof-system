"""Command line interface: ``python -m dpc <command>`` (or ``pixi run dpc <command>``)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from dpc.analysis import Analysis, assign_domains, graph_diff, merge, reverse_degree, summarize
from dpc.audit import AuditLog
from dpc.ingest import Submission, ingest
from dpc.ingest.volume import ingest_in_volume
from dpc.lean.executor import DockerExecutor, HostExecutor, LeanExecutor, Limits
from dpc.requirements import load_requirements

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

    p = sub.add_parser("requirements", help="requirement catalogue statistics")
    p.set_defaults(func=cmd_requirements)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
