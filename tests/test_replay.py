"""Kernel replay of the submission's own modules (docs/adr/0009).

Lean does not re-check `.olean` files on import, and a build runs the
submission's code. The replay sends every declaration that is not loaded from
the toolchain or an official package through the kernel again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dpc.analysis import Analysis
from dpc.audit import AuditLog
from dpc.ingest import Submission, ingest
from dpc.lean.executor import REPO_ROOT, HostExecutor, _replay_args
from dpc.lean.project import Manifest, Package, lean_path, runtime_env, trusted_lean_path
from dpc.lean.replay import SCHEMA, ReplayReport

from conftest import copy_fixture, make_git_repo

MATHLIB = Package(name="mathlib", type="git", rev="a" * 40,
                  url="https://github.com/leanprover-community/mathlib4")
OTHER = Package(name="carleson", type="git", rev="b" * 40,
                url="https://github.com/fpvandoorn/carleson")


# ------------------------------------------------------------- search path
@pytest.mark.req("SR-03", "SR-20")
def test_trusted_entries_come_first_on_the_search_path() -> None:
    """Lean loads a module from the first entry containing its root name. If the
    submission's build directory came first, a build could place forged copies
    of `Mathlib` there and the analysis would count them as hardened."""
    manifest = Manifest(packages=(OTHER, MATHLIB))
    paths = lean_path(Path("/work"), manifest)
    trusted = trusted_lean_path(Path("/work"), manifest)
    assert trusted == [str(Path("/work/.lake/packages/mathlib/.lake/build/lib/lean"))]
    assert paths[0] == trusted[0]
    assert paths[1] == str(Path("/work/.lake/build/lib/lean"))
    assert paths[2].endswith(str(Path("carleson/.lake/build/lib/lean")))


@pytest.mark.req("SR-03", "SR-20")
def test_the_toolchain_library_comes_first() -> None:
    env = runtime_env(Path("/toolchain"), ["/work/.lake/build/lib/lean"], base={})
    first = env["LEAN_PATH"].split(";" if ";" in env["LEAN_PATH"] else ":")[0]
    assert first == str(Path("/toolchain/lib/lean"))
    script = (REPO_ROOT / "sandbox" / "run-tool.sh").read_text("utf-8")
    assert 'export LEAN_PATH="$LEAN_SYSROOT/lib/lean${LEAN_PATH:+:$LEAN_PATH}"' in script


def test_replay_arguments() -> None:
    assert _replay_args(["A"], ["/t"], 0, "/out/r.jsonl") == [
        "--root", "A", "--trusted", "/t", "--jobs", "1", "--out", "/out/r.jsonl"]


# ------------------------------------------------------------- report model
def _report(origins: dict[str, str], failing: dict[str, str] | None = None) -> ReplayReport:
    failing = failing or {}
    records: list[dict[str, Any]] = [{
        "kind": "header", "schema": SCHEMA, "toolchain": "4.33.1", "roots": ["Basic"],
        "trusted": [], "core": "/toolchain/lib/lean", "jobs": 2}]
    for module, origin in origins.items():
        records.append({"kind": "module", "module": module, "origin": origin, "entry": "/x",
                        "constants": 3, "skipped": 0, "ok": module not in failing,
                        "error": failing.get(module)})
    return ReplayReport.from_records(records)


def _modules(analysis: Analysis) -> set[str]:
    return {d.module for d in analysis.decls.values() if d.module}


@pytest.mark.req("SR-02")
def test_report_lists_failures_and_counts(basic_core: Analysis) -> None:
    origins = {m: ("replayed" if m == "Basic" else "core") for m in _modules(basic_core)}
    report = _report(origins, failing={"Basic": "(kernel) declaration type mismatch"})
    assert [m.module for m in report.failures] == ["Basic"]
    summary = report.summary()
    assert summary["replayed"] == 1 and summary["constants_replayed"] == 3
    assert summary["failures"] == [{"module": "Basic",
                                    "error": "(kernel) declaration type mismatch"}]
    assert report.uncovered(basic_core) == []
    assert report.untrusted_hardened(basic_core) == []


@pytest.mark.req("SR-03")
def test_hardened_modules_from_untrusted_locations_are_reported(basic_core: Analysis) -> None:
    """The analysis decides "hardened" by module name; the replay knows where the
    file actually came from. A name alone must not remove anything from TCB_new."""
    origins = {m: ("replayed" if m in ("Basic", "Init.Prelude") else "core")
               for m in _modules(basic_core)}
    assert _report(origins).untrusted_hardened(basic_core) == ["Init.Prelude"]


def test_modules_the_replay_did_not_see_are_reported(basic_core: Analysis) -> None:
    origins = {m: "core" for m in _modules(basic_core) if m != "Basic"}
    assert _report(origins).uncovered(basic_core) == ["Basic"]


def test_report_schema_is_checked() -> None:
    with pytest.raises(ValueError, match="unsupported schema"):
        ReplayReport.from_records([{"kind": "header", "schema": "dpc.replay/0",
                                    "toolchain": "", "roots": [], "trusted": [], "core": "",
                                    "jobs": 1}])
    with pytest.raises(ValueError, match="empty"):
        ReplayReport.from_records([])


# ------------------------------------------------------------- with Lean
@pytest.mark.lean
@pytest.mark.req("SR-02", "SR-20")
def test_honest_project_replays_cleanly(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("basic", tmp_path)
    assert host_executor.build(project, ["Basic"]).ok
    out = tmp_path / "replay.jsonl"
    result = host_executor.replay(project, roots=["Basic"], out=out)
    assert result.ok, result.output
    report = ReplayReport.load(out)
    assert not report.failures
    assert [m.module for m in report.replayed] == ["Basic"]
    assert report.replayed[0].constants > 0
    assert {m.origin for m in report.modules if m.module != "Basic"} == {"core"}


@pytest.mark.lean
@pytest.mark.req("SR-02", "SR-19", "SR-20")
def test_forged_proof_passes_the_build_and_the_axiom_check_but_not_the_replay(
    host_executor: HostExecutor, tmp_path: Path
) -> None:
    """`Replay.bogus : False` is added with `debug.skipKernelTC`. The build
    succeeds, and `Replay.main : False` depends on no axiom at all."""
    repo, commit = make_git_repo(tmp_path, "replay")
    submission = Submission(repo_url=str(repo), commit=commit, root="Replay.main",
                            root_module="Replay", paper_ref="fixture")
    with AuditLog(tmp_path / "audit.sqlite") as log:
        result = ingest(submission, workdir=tmp_path / "work", executor=host_executor, log=log)
        events = list(log.entries())
    assert result.summary.findings == ()  # the axiom check sees nothing
    assert result.kernel_failures == ("Replay.Forged",)
    assert result.blocking
    forged = next(m for m in result.replay.modules if m.module == "Replay.Forged")
    assert "Replay.bogus" in (forged.error or "") and "kernel" in (forged.error or "")
    checks = {m.module: m for m in result.replay.replayed}
    assert checks["Replay.Honest"].ok and checks["Replay.Honest"].skipped == 3  # partial, unsafe
    # A file of the module system: the private declarations are replayed too.
    assert checks["Replay.Modular"].ok and checks["Replay.Modular"].constants == 4
    kinds = [e.kind for e in events]
    assert kinds.index("kernel.replayed") < kinds.index("analysis.completed")
    finding = next(e.payload for e in events if e.kind == "finding.kernel")
    assert finding["module"] == "Replay.Forged" and finding["blocking"] is True


@pytest.mark.lean
@pytest.mark.req("SR-03", "SR-20")
def test_planted_core_modules_in_the_build_directory_are_never_loaded(
    host_executor: HostExecutor, tmp_path: Path
) -> None:
    """A build may write anything into its own `.lake/build`. A directory `Init`
    there must not shadow the toolchain's `Init`: here the planted files are
    garbage, so loading them would fail."""
    project = copy_fixture("basic", tmp_path)
    assert host_executor.build(project, ["Basic"]).ok
    lib = project / ".lake" / "build" / "lib" / "lean"
    (lib / "Init").mkdir()
    for planted in (lib / "Init.olean", lib / "Init" / "Prelude.olean"):
        planted.write_bytes(b"not an olean")
    out = tmp_path / "replay.jsonl"
    assert host_executor.replay(project, roots=["Basic"], out=out).ok
    report = ReplayReport.load(out)
    assert report.origin("Init.Prelude") == "core" and not report.failures
    analysis_out = tmp_path / "core.jsonl"
    analysed = host_executor.analyze(project, root="Basic.main_theorem", imports=["Basic"],
                                     mode="core", out=analysis_out)
    assert analysed.ok, analysed.output
    header = json.loads(analysis_out.read_text("utf-8").splitlines()[0])
    assert header["root"] == "Basic.main_theorem"
