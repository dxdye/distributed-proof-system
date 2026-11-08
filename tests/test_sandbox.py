"""Sandbox (SR-20): isolation flags by inspection, red-team and parity tests in Docker."""

from __future__ import annotations

from pathlib import Path

import pytest

from dpc.lean.executor import DockerExecutor, Limits, Mount

from conftest import DATA, copy_fixture

pytestmark = pytest.mark.req("SR-20")


def _argv(executor: DockerExecutor, mounts: list[Mount]) -> list[str]:
    return executor.run_argv("img", ["lake", "build"], mounts=mounts, container="c1")


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def test_isolation_flags() -> None:
    executor = DockerExecutor(limits=Limits(cpus=1.5, memory="4g", pids=256))
    argv = _argv(executor, [])
    assert _flag(argv, "--network") == "none"
    assert "--read-only" in argv
    assert "--rm" in argv
    assert _flag(argv, "--cap-drop") == "ALL"
    assert _flag(argv, "--security-opt") == "no-new-privileges"
    assert _flag(argv, "--user") == "1000:1000"
    assert _flag(argv, "--cpus") == "1.5"
    assert _flag(argv, "--memory") == _flag(argv, "--memory-swap") == "4g"
    assert _flag(argv, "--pids-limit") == "256"
    assert argv[-3:] == ["img", "lake", "build"]


def test_build_mounts_source_read_only(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    (project / ".lake" / "packages").mkdir(parents=True)
    mounts = DockerExecutor().build_mounts(project)
    by_target = {m.target: m for m in mounts}
    assert by_target["/work"].read_only
    assert not by_target["/work/.lake"].read_only
    assert by_target["/work/.lake/packages"].read_only
    assert "readonly" in by_target["/work"].arg()


def test_analysis_mounts_everything_read_only_but_output(tmp_path: Path) -> None:
    mounts = DockerExecutor().analyze_mounts(tmp_path / "repo", tmp_path / "out")
    assert [m.read_only for m in mounts] == [True, False]
    assert mounts[1].target == "/out"


# ------------------------------------------------------------------ docker
@pytest.mark.docker
def test_redteam_build_cannot_write_sources_or_reach_network(tmp_path: Path) -> None:
    project = copy_fixture("redteam", tmp_path)
    result = DockerExecutor().build(project, ["Redteam"])
    assert result.ok, result.output
    assert "WRITE_SOURCE:FAILED" in result.output
    assert "WRITE_SYSTEM:FAILED" in result.output
    assert "NET:FAILED" in result.output
    assert "WRITE_BUILD:OK" in result.output  # only the build directory is writable
    assert not (project / "PWNED.txt").exists()


@pytest.mark.docker
@pytest.mark.req("SR-01", "SR-03")
def test_sandboxed_analysis_equals_recorded_host_analysis(tmp_path: Path) -> None:
    """Parity: Linux container and the recording host produce byte-identical
    output, i.e. hashes and ordering are platform-independent."""
    project = copy_fixture("basic", tmp_path)
    executor = DockerExecutor()
    build = executor.build(project, ["Basic"])
    assert build.ok, build.output
    for mode in ("core", "metadata"):
        out = tmp_path / "out" / f"{mode}.jsonl"
        result = executor.analyze(project, root="Basic.main_theorem", imports=["Basic"],
                                  mode=mode, out=out)  # type: ignore[arg-type]
        assert result.ok, result.output
        assert out.read_bytes() == (DATA / "basic" / f"{mode}.jsonl").read_bytes(), mode
