"""Ingest pipeline (operational scenario OS-1, concept §16 steps 1-2).

    submission → fetch (trusted, network) → build (sandbox) → analyse twice
    (sandbox: core + metadata) → cross-check → summary → audit log

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


def artifact_key(toolchain: str, manifest_sha256: str, commit: str) -> str:
    """Content address of a built environment (docs/adr/0003)."""
    return sha256_hex(
        canonical_json({"toolchain": toolchain, "manifest": manifest_sha256, "commit": commit})
    )


def _file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


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
    return IngestResult(project, paths["core"], paths["metadata"], analysis, summary, key)
