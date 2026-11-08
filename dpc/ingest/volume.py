"""Ingest of real-world submissions inside a Docker volume (case studies).

Same steps and audit events as :mod:`dpc.ingest.pipeline`, plus the Mathlib
cache step and the provenance check of the hardened set.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dpc.analysis import Analysis, AnalysisMismatch, Summary, merge, summarize
from dpc.analysis.hardening import unverified_hardened_modules
from dpc.audit import AuditLog, canonical_json, sha256_hex
from dpc.ingest.pipeline import IngestError, artifact_key
from dpc.ingest.submission import Submission
from dpc.lean.executor import DockerExecutor, RunResult
from dpc.lean.workspace import VolumeWorkspace, compare_digests


@dataclass(frozen=True)
class VolumeIngestResult:
    volume: str
    core_path: Path
    metadata_path: Path
    analysis: Analysis
    summary: Summary
    artifact_key: str
    unverified_hardened: tuple[str, ...]


CACHE_ATTEMPTS = 3


def volume_name(submission: Submission) -> str:
    """Deterministic, so a rerun reuses the fetched sources and caches."""
    origin = sha256_hex(f"{submission.repo_url}\n{submission.project_dir}".encode())[:8]
    return f"dpc-ws-{submission.commit[:12]}-{origin}"


def _digest_of(digests: dict[str, str]) -> str:
    return sha256_hex(canonical_json(dict(sorted(digests.items()))))


def _step(result: RunResult, step: str, log: AuditLog, log_dir: Path | None = None) -> None:
    """Record a step; the full output goes to ``log_dir/<step>.log`` (its hash is
    in the audit log, so the file can be verified later)."""
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{step}.log").write_text(result.output, encoding="utf-8")
    log.append(
        f"{step}.completed",
        {
            "ok": result.ok,
            "executor": "docker-volume",
            "duration_s": int(result.duration_s),
            "timed_out": result.timed_out,
            "output_sha256": sha256_hex(result.output.encode("utf-8")),
        },
    )
    if not result.ok:
        errors = [line for line in result.output.splitlines() if line.startswith("error")]
        hint = f" (full output: {log_dir / (step + '.log')})" if log_dir else ""
        raise IngestError(f"{step} failed (exit {result.returncode}){hint}:\n"
                          + "\n".join(errors[:20]) + "\n…\n" + result.output.strip()[-2000:])


def ingest_in_volume(
    submission: Submission, *, executor: DockerExecutor, log: AuditLog, out_dir: Path
) -> VolumeIngestResult:
    logs = out_dir.parent / "logs"
    log.append("submission.received", submission.model_dump())
    ws = VolumeWorkspace(executor, volume_name(submission), submission.project_dir)
    ws.create()

    fetched = ws.fetch(submission.repo_url, submission.commit, submission.patch_dir)
    manifest = fetched.manifest
    key = artifact_key(fetched.toolchain, fetched.manifest_sha256, submission.commit)
    log.append(
        "repo.fetched",
        {
            "commit": submission.commit,
            "toolchain": fetched.toolchain,
            "manifest_sha256": fetched.manifest_sha256,
            "packages": [{"name": p.name, "rev": p.rev, "url": p.url} for p in manifest.packages],
            "artifact_key": key,
            "volume": ws.volume,
            "reused": fetched.reused,
            "dependency_patches": [
                {"package": p.package, "file": p.file, "sha256": p.sha256}
                for p in fetched.patches
            ],
        },
    )

    image = executor.ensure_image(fetched.toolchain)
    snapshot = ws.trusted_snapshot(image)
    if snapshot is None:
        # Invariant: trusted steps only run in a volume that never saw foreign code.
        if ws.untrusted_ran(image):
            raise IngestError(f"volume {ws.volume} ran untrusted code but has no trusted "
                              "snapshot; remove it and start from scratch")
        # Downloads can fail transiently; the step is idempotent and trusted.
        cache = None
        for attempt in range(1, CACHE_ATTEMPTS + 1):
            cache = ws.fetch_cache(image, manifest)
            if cache is None or cache.ok or attempt == CACHE_ATTEMPTS:
                break
            log.append("cache.retry", {"artifact_key": key, "attempt": attempt,
                                       "output_sha256": sha256_hex(cache.output.encode())})
        if cache is not None:
            _step(cache, "cache", log, logs)
        heads = ws.package_heads(image, manifest)
        drift = sorted(p.name for p in manifest.packages if heads.get(p.name) != p.rev)
        if drift:
            log.append("repo.drift", {"artifact_key": key, "packages": drift})
            raise IngestError(f"dependencies no longer at their pinned revisions: {drift}")
        # Snapshot of the hardened set after the last trusted step (docs/adr/0005).
        before = ws.digest_hardened(image, manifest, save=True)
        log.append("hardened.snapshot", {"artifact_key": key, "files": len(before),
                                         "sha256": _digest_of(before)})
    else:
        # Reused volume: verify against the stored snapshot before anything runs.
        before = snapshot
        current = compare_digests(before, ws.digest_hardened(image, manifest))
        log.append("hardened.reverified", {"artifact_key": key, "ok": current.ok,
                                           "changed": list(current.changed[:50]),
                                           "added": list(current.added[:50])})
        if not current.ok:
            raise IngestError(f"volume {ws.volume} no longer matches its trusted snapshot; "
                              "remove it and start from scratch")

    ws.mark_untrusted(image)
    build = ws.build(image, manifest, [submission.root_module])
    after = ws.digest_hardened(image, manifest)
    integrity = compare_digests(before, after)
    log.append("hardened.verified", {
        "artifact_key": key, "ok": integrity.ok, "changed": list(integrity.changed[:50]),
        "added": list(integrity.added[:50]), "sha256": _digest_of(after),
    })
    if not integrity.ok:
        raise IngestError(
            "the build modified hardened packages — refusing to analyse: "
            f"{len(integrity.changed)} changed, {len(integrity.added)} added, "
            f"e.g. {(integrity.changed + integrity.added)[:5]}"
        )
    _step(build, "build", log, logs)

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {mode: out_dir / f"{mode}.jsonl" for mode in ("core", "metadata")}
    for mode, path in paths.items():
        result = ws.analyze(image, manifest, root=submission.root,
                            imports=[submission.root_module], mode=mode,  # type: ignore[arg-type]
                            out=path)
        _step(result, f"analysis_{mode}", log, logs)

    try:
        analysis = merge(Analysis.load(paths["core"]), Analysis.load(paths["metadata"]))
    except AnalysisMismatch as exc:
        log.append("analysis.mismatch", {"artifact_key": key, "reason": str(exc)})
        raise IngestError(f"core and metadata analysis disagree: {exc}") from exc

    unverified = unverified_hardened_modules(analysis, ws.official_modules(image, manifest))
    summary = summarize(analysis)
    log.append(
        "analysis.completed",
        {
            "artifact_key": key,
            "core_sha256": sha256_hex(paths["core"].read_bytes()),
            "metadata_sha256": sha256_hex(paths["metadata"].read_bytes()),
            "summary": summary.as_dict(),
            "unverified_hardened_modules": unverified,
        },
    )
    for finding in summary.findings:
        log.append("finding.axiom", {"artifact_key": key, "axiom": finding.axiom,
                                     "kind": finding.kind, "blocking": finding.blocking})
    if unverified:
        log.append("finding.hardening", {"artifact_key": key, "modules": unverified,
                                         "blocking": True})
    return VolumeIngestResult(ws.volume, paths["core"], paths["metadata"], analysis, summary,
                              key, tuple(unverified))
