"""End-to-end tests with the real Lean toolchain on the trusted fixtures.

Set ``DPC_UPDATE_GOLDEN=1`` to re-record ``tests/data/basic`` after an
intentional analyzer change.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dpc.analysis import Analysis, graph_diff, merge, units
from dpc.lean.executor import HostExecutor

from conftest import DATA, copy_fixture

pytestmark = pytest.mark.lean


def _analyse(executor: HostExecutor, project: Path, out: Path) -> tuple[Path, Path]:
    build = executor.build(project, ["Basic"])
    assert build.ok, build.output
    paths = (out / "core.jsonl", out / "metadata.jsonl")
    for mode, path in zip(("core", "metadata"), paths, strict=True):
        result = executor.analyze(project, root="Basic.main_theorem", imports=["Basic"],
                                  mode=mode, out=path)  # type: ignore[arg-type]
        assert result.ok, result.output
    return paths


def _variant(tmp_path: Path, name: str, old: str, new: str) -> Path:
    project = copy_fixture("basic", tmp_path / name)
    source = project / "Basic.lean"
    text = source.read_text("utf-8")
    assert old in text
    source.write_text(text.replace(old, new), "utf-8")
    return project


@pytest.mark.req("SR-03")
def test_analysis_matches_recorded_output(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("basic", tmp_path)
    core, metadata = _analyse(host_executor, project, tmp_path / "out")
    if os.environ.get("DPC_UPDATE_GOLDEN") == "1":
        for path in (core, metadata):
            (DATA / "basic" / path.name).write_bytes(path.read_bytes())
    for path in (core, metadata):
        assert path.read_bytes() == (DATA / "basic" / path.name).read_bytes(), path.name


@pytest.mark.req("SR-03")
def test_analysis_is_deterministic(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("basic", tmp_path)
    first, _ = _analyse(host_executor, project, tmp_path / "a")
    second, _ = _analyse(host_executor, project, tmp_path / "b")
    assert first.read_bytes() == second.read_bytes()


def _load(paths: tuple[Path, Path]) -> Analysis:
    return merge(Analysis.load(paths[0]), Analysis.load(paths[1]))


@pytest.mark.req("SR-03", "SR-16")
def test_changing_a_proof_leaves_the_tcb_unchanged(
    host_executor: HostExecutor, tmp_path: Path
) -> None:
    """Property from verification §11.2: a different proof of the main theorem
    must not change its TCB, and must not re-open any class-A ticket."""
    old = _load(_analyse(host_executor, copy_fixture("basic", tmp_path / "old"), tmp_path / "o"))
    project = _variant(
        tmp_path, "new",
        "/-- Main theorem of the fixture. -/",
        "theorem helper2 (n : Nat) : 2 * n = double n := by\n  unfold double\n  omega\n\n"
        "/-- Main theorem of the fixture. -/",
    )
    source = project / "Basic.lean"
    source.write_text(source.read_text("utf-8").replace("⟨_, helper _⟩", "⟨_, helper2 _⟩"),
                      "utf-8")
    new = _load(_analyse(host_executor, project, tmp_path / "n"))

    tcb_old = {n: d.meaning_hash for n, d in old.decls.items() if d.in_tcb}
    tcb_new = {n: d.meaning_hash for n, d in new.decls.items() if d.in_tcb}
    assert tcb_old == tcb_new

    diff = graph_diff(old, new)
    assert "Basic.main_theorem" in diff.proof_only_changed
    class_a = {u for u, x in units(new).items() if x.in_tcb}
    assert not diff.invalidated_units & class_a
    # The proof now uses helper2 (new class-B ticket) instead of helper.
    assert "Basic.helper2" in diff.invalidated_units


@pytest.mark.req("SR-16")
def test_changing_a_definition_invalidates_its_dependents(
    host_executor: HostExecutor, tmp_path: Path
) -> None:
    old = _load(_analyse(host_executor, copy_fixture("basic", tmp_path / "old"), tmp_path / "o"))
    project = _variant(tmp_path, "new", "def double (n : Nat) : Nat := n + n",
                       "def double (n : Nat) : Nat := 2 * n")
    new = _load(_analyse(host_executor, project, tmp_path / "n"))
    diff = graph_diff(old, new)
    assert "Basic.double" in diff.meaning_changed
    assert {"Basic.double", "Basic.isEven", "Basic.main_theorem", "Basic.helper"} <= (
        diff.invalidated_units
    )
    untouched = {"Basic.Point", "Basic.Color", "Basic.sumTo", "Basic.secret",
                 "Basic.instAddPoint", "Basic.Color.toNat"}
    assert untouched <= diff.kept_units


@pytest.mark.req("SR-16")
def test_renaming_bound_variables_is_not_a_change(
    host_executor: HostExecutor, tmp_path: Path
) -> None:
    """Content hashes are α-invariant: renaming a bound variable keeps every
    ticket, whereas the definition-change test above invalidates them."""
    old = _load(_analyse(host_executor, copy_fixture("basic", tmp_path / "old"), tmp_path / "o"))
    project = _variant(tmp_path, "new", "def double (n : Nat) : Nat := n + n",
                       "def double (m : Nat) : Nat := m + m")
    new = _load(_analyse(host_executor, project, tmp_path / "n"))
    diff = graph_diff(old, new)
    assert not diff.meaning_changed
    assert not diff.invalidated_units


def test_sha256_known_answers(host_executor: HostExecutor) -> None:
    """FIPS 180-4 test vectors for the Lean SHA-256 used in content hashes."""
    import subprocess

    from dpc.lean.project import runtime_env

    exe = host_executor.analyzer_exe("leanprover/lean4:v4.33.1")
    sysroot = subprocess.run(["lean", "--print-prefix"], cwd=exe.parents[3], check=True,
                             capture_output=True, text=True).stdout.strip()
    out = subprocess.run([str(exe), "--selftest"], env=runtime_env(Path(sysroot), []),
                         check=True, capture_output=True, text=True).stdout.split()
    assert out[0::2] == [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
    ]


def test_unknown_root_fails_cleanly(host_executor: HostExecutor, tmp_path: Path) -> None:
    project = copy_fixture("basic", tmp_path)
    assert host_executor.build(project, ["Basic"]).ok
    result = host_executor.analyze(project, root="Basic.nope", imports=["Basic"], mode="core",
                                   out=tmp_path / "x.jsonl")
    assert not result.ok
    assert "not found" in result.output


def test_host_executor_requires_explicit_trust(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        HostExecutor(trusted=False, cache_dir=tmp_path)


@pytest.mark.req("SR-01")
def test_missing_toolchain_pin_is_rejected(host_executor: HostExecutor, tmp_path: Path) -> None:
    from dpc.lean.project import ProjectError, read_toolchain

    project = copy_fixture("basic", tmp_path)
    (project / "lean-toolchain").unlink()
    with pytest.raises(ProjectError):
        read_toolchain(project)
