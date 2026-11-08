"""Ingest pipeline: fetch at pinned commit, build, analyse, audit log."""

from __future__ import annotations

from pathlib import Path

import pytest

from dpc.audit import AuditLog
from dpc.ingest import FetchError, Submission, clone_at_commit, fetch_dependencies, ingest
from dpc.lean.executor import DockerExecutor, HostExecutor, LeanExecutor
from dpc.lean.project import Manifest, Package, ProjectError

from conftest import git, make_git_repo


def test_submission_requires_full_commit_hash() -> None:
    with pytest.raises(ValueError):
        Submission(repo_url="x", commit="abc123", root="A.b", root_module="A")


@pytest.mark.req("SR-01")
def test_clone_checks_out_exactly_the_pinned_commit(tmp_path: Path) -> None:
    repo, first = make_git_repo(tmp_path, "basic")
    (repo / "Basic.lean").write_text("-- changed later\n", "utf-8")
    git("commit", "--quiet", "-am", "later", cwd=repo)
    dest = tmp_path / "clone"
    clone_at_commit(str(repo), first, dest)
    assert git("rev-parse", "HEAD", cwd=dest) == first
    assert "main_theorem" in (dest / "Basic.lean").read_text("utf-8")


@pytest.mark.req("SR-01")
def test_missing_manifest_is_rejected(tmp_path: Path) -> None:
    repo, commit = make_git_repo(tmp_path, "basic")
    git("rm", "--quiet", "lake-manifest.json", cwd=repo)
    git("commit", "--quiet", "-m", "drop manifest", cwd=repo)
    commit = git("rev-parse", "HEAD", cwd=repo)
    submission = Submission(repo_url=str(repo), commit=commit, root="Basic.main_theorem",
                            root_module="Basic")
    executor = HostExecutor(trusted=True, cache_dir=tmp_path / "cache")
    with AuditLog(tmp_path / "audit.sqlite") as log, pytest.raises(ProjectError):
        ingest(submission, workdir=tmp_path / "work", executor=executor, log=log)


@pytest.mark.req("SR-01")
def test_unpinned_dependencies_are_rejected(tmp_path: Path) -> None:
    manifest = Manifest(packages=(Package(name="dep", type="git", url="x", rev="main"),))
    with pytest.raises(FetchError, match="not pinned"):
        fetch_dependencies(tmp_path, manifest)
    path_dep = Manifest(packages=(Package(name="dep", type="path", dir="../dep"),))
    with pytest.raises(FetchError, match="only git"):
        fetch_dependencies(tmp_path, path_dep)


def _ingest(tmp_path: Path, executor: LeanExecutor) -> None:
    repo, commit = make_git_repo(tmp_path, "basic")
    submission = Submission(repo_url=str(repo), commit=commit, root="Basic.main_theorem",
                            root_module="Basic", paper_ref="fixture")
    with AuditLog(tmp_path / "audit.sqlite") as log:
        result = ingest(submission, workdir=tmp_path / "work", executor=executor, log=log)
        kinds = [e.kind for e in log.entries()]
        assert kinds == [
            "submission.received", "repo.fetched", "build.completed",
            "analysis_core.completed", "analysis_metadata.completed", "analysis.completed",
        ]
        assert log.verify().ok
        completed = list(log.entries())[-1].payload
    assert len(result.summary.tcb_new_units) == 10
    assert completed["summary"]["tcb_new_units"] == 10
    assert completed["artifact_key"] == result.artifact_key


@pytest.mark.lean
@pytest.mark.req("SR-01", "SR-19")
def test_ingest_on_host_with_trusted_fixture(tmp_path: Path, host_executor: HostExecutor) -> None:
    _ingest(tmp_path, host_executor)


@pytest.mark.docker
@pytest.mark.req("SR-01", "SR-19", "SR-20")
def test_ingest_in_sandbox(tmp_path: Path) -> None:
    _ingest(tmp_path, DockerExecutor())
