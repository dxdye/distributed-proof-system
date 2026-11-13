"""Ingest pipeline (operational scenario OS-1, concept §16 steps 1-2).

    submission → fetch (trusted, network) → build (sandbox) → kernel replay
    (sandbox) → analyse twice (sandbox: core + metadata) → cross-check →
    summary → audit log

Every step is recorded in the audit log, so the result can later be
re-derived from the log alone (SR-17).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dpc.analysis import Analysis, AnalysisMismatch, Summary, merge, summarize
from dpc.audit import AuditLog, canonical_json, sha256_hex
from dpc.ingest.fetch import clone_at_commit, fetch_dependencies
from dpc.ingest.submission import Submission
from dpc.lean.executor import LeanExecutor, RunResult
from dpc.lean.project import manifest_digest, read_manifest, read_toolchain
from dpc.lean.replay import ReplayReport


class IngestError(RuntimeError):
    """The submission could not be ingested; the reason is in the audit log."""


@dataclass(frozen=True)
class IngestResult:
    project: Path
    core_path: Path
    metadata_path: Path
    analysis: Analysis
    summary: Summary
    artifact_key: str
    replay: ReplayReport
    kernel_failures: tuple[str, ...] = ()  # modules the kernel replay rejected
    untrusted_hardened: tuple[str, ...] = ()  # "hardened" modules from untrusted places

    @property
    def blocking(self) -> bool:
        return self.summary.blocking or bool(self.kernel_failures or self.untrusted_hardened)


def artifact_key(toolchain: str, manifest_sha256: str, commit: str) -> str:
    """Content address of a built environment (docs/adr/0003)."""
    return sha256_hex(
        canonical_json({"toolchain": toolchain, "manifest": manifest_sha256, "commit": commit})
    )


def _file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def record_replay(log: AuditLog, key: str, path: Path) -> ReplayReport:
    """Log the kernel replay (docs/adr/0009). Every module the kernel rejects is
    a blocking finding: its `.olean` contains declarations that were never checked."""
    report = ReplayReport.load(path)
    log.append("kernel.replayed", {"artifact_key": key, "report_sha256": _file_sha256(path),
                                   **report.summary()})
    for failure in report.failures:
        log.append("finding.kernel", {"artifact_key": key, "module": failure.module,
                                      "error": (failure.error or "")[:500], "blocking": True})
    return report


def check_replay_against(log: AuditLog, key: str, report: ReplayReport,
                         analysis: Analysis) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Cross-check replay and analysis: every analysed module must have been
    seen by the replay, and no module the analysis counts as hardened may come
    from an untrusted location. Returns (kernel failures, untrusted hardened)."""
    uncovered = report.uncovered(analysis)
    for module in uncovered:
        log.append("finding.kernel", {"artifact_key": key, "module": module,
                                      "error": "not covered by the kernel replay",
                                      "blocking": True})
    untrusted = report.untrusted_hardened(analysis)
    if untrusted:
        log.append("finding.hardening", {"artifact_key": key, "modules": untrusted,
                                         "reason": "loaded from an untrusted location",
                                         "blocking": True})
    failures = sorted({m.module for m in report.failures} | set(uncovered))
    return tuple(failures), tuple(untrusted)


def _check(result: RunResult, step: str, log: AuditLog, executor: LeanExecutor) -> None:
    log.append(
        f"{step}.completed",
        {
            "ok": result.ok,
            "executor": executor.name,
            "duration_s": int(result.duration_s),
            "timed_out": result.timed_out,
            "output_sha256": sha256_hex(result.output.encode("utf-8")),
        },
    )
    if not result.ok:
        tail = result.output.strip()[-2000:]
        raise IngestError(f"{step} failed (exit {result.returncode}):\n{tail}")


def ingest(
    submission: Submission, *, workdir: Path, executor: LeanExecutor, log: AuditLog
) -> IngestResult:
    log.append("submission.received", submission.model_dump())
    project = workdir / "repo"
    clone_at_commit(submission.repo_url, submission.commit, project)
    toolchain = read_toolchain(project)
    manifest = read_manifest(project, required=True)
    key = artifact_key(toolchain, manifest_digest(project), submission.commit)
    fetched = fetch_dependencies(project, manifest)
    log.append(
        "repo.fetched",
        {
            "commit": submission.commit,
            "toolchain": toolchain,
            "manifest_sha256": manifest_digest(project),
            "packages": [{"name": p.name, "rev": p.rev, "url": p.url} for p in fetched],
            "artifact_key": key,
        },
    )

    _check(executor.build(project, [submission.root_module]), "build", log, executor)

    out_dir = workdir / "analysis"
    replay_path = out_dir / "replay.jsonl"
    _check(executor.replay(project, roots=[submission.root_module], out=replay_path),
           "replay", log, executor)
    replay = record_replay(log, key, replay_path)

    paths = {mode: out_dir / f"{mode}.jsonl" for mode in ("core", "metadata")}
    for mode, path in paths.items():
        result = executor.analyze(
            project, root=submission.root, imports=[submission.root_module],
            mode=mode, out=path,  # type: ignore[arg-type]
        )
        _check(result, f"analysis_{mode}", log, executor)

    core = Analysis.load(paths["core"])
    metadata = Analysis.load(paths["metadata"])
    try:
        analysis = merge(core, metadata)
    except AnalysisMismatch as exc:
        log.append("analysis.mismatch", {"artifact_key": key, "reason": str(exc)})
        raise IngestError(f"core and metadata analysis disagree: {exc}") from exc

    summary = summarize(analysis)
    log.append(
        "analysis.completed",
        {
            "artifact_key": key,
            "core_sha256": _file_sha256(paths["core"]),
            "metadata_sha256": _file_sha256(paths["metadata"]),
            "summary": summary.as_dict(),
        },
    )
    for finding in summary.findings:  # SR-02: every non-standard axiom blocks
        log.append(
            "finding.axiom",
            {"artifact_key": key, "axiom": finding.axiom, "kind": finding.kind,
             "blocking": finding.blocking},
        )
    failures, untrusted = check_replay_against(log, key, replay, analysis)
    return IngestResult(project, paths["core"], paths["metadata"], analysis, summary, key,
                        replay, failures, untrusted)
