"""What a result relies on (proposal C-29): the trusted assumptions of an
ingested submission, for the report and the progress page.

Read from the ingest's own records: the analysis header (toolchain, axioms of
the main theorem), the kernel replay report (what was re-checked and what was
trusted by location), and the ingest audit log (the pinned official packages,
the integrity check of the hardened files). Nothing is re-run here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dpc.analysis.model import Analysis
from dpc.audit import AuditLog
from dpc.lean.project import OFFICIAL_PACKAGES, normalize_url
from dpc.lean.replay import ReplayReport


def _official(name: str, url: str | None) -> bool:
    return url is not None and OFFICIAL_PACKAGES.get(name) == normalize_url(url)


def trust_basis(workdir: Path, commit: str, ingest_log: AuditLog | None = None
                ) -> dict[str, Any]:
    """Fields of ``BasisRecorded`` (without the submission id)."""
    header = Analysis.load(workdir / "analysis" / "core.jsonl").header
    out: dict[str, Any] = {"toolchain": header.toolchain, "axioms": list(header.axioms)}
    replay_path = workdir / "analysis" / "replay.jsonl"
    if replay_path.is_file():
        report = ReplayReport.load(replay_path)
        replayed = report.replayed
        out |= {
            "replayed": True,
            "modules_replayed": len(replayed),
            "constants_replayed": sum(m.constants for m in replayed),
            "replay_failures": len(report.failures),
            "modules_trusted": sum(m.origin == "trusted" for m in report.modules),
            "modules_core": sum(m.origin == "core" for m in report.modules),
        }
    if ingest_log is not None:
        key = None
        for entry in ingest_log.entries():  # the latest ingest of this commit wins
            p = entry.payload
            if entry.kind == "repo.fetched" and p.get("commit") == commit:
                key = p.get("artifact_key")
                out["libraries"] = [
                    {"name": pkg["name"], "url": pkg["url"], "rev": pkg["rev"]}
                    for pkg in p.get("packages", [])
                    if _official(pkg["name"], pkg.get("url"))]
            elif key is not None and p.get("artifact_key") == key:
                if entry.kind == "hardened.snapshot":
                    out["hardened_files"] = p.get("files")
                elif entry.kind == "hardened.verified":
                    out["hardened_unchanged"] = bool(p.get("ok"))
    return out
