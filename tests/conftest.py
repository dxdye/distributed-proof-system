"""Shared fixtures.

Fast tests run fully offline against recorded analyzer output in
``tests/data`` (record/replay). Tests marked ``lean`` run the real toolchain on
the fixtures in ``lean/fixtures``; tests marked ``docker`` need a running Docker
daemon. Both are skipped automatically when the tool is missing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest

from dpc.analysis import Analysis, merge
from dpc.lean.executor import HostExecutor

pytest_plugins = ["dpc.tools.traceability"]

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
FIXTURES = ROOT / "lean" / "fixtures"
CACHE = ROOT / ".dpc-cache"


def has_lean() -> bool:
    return shutil.which("lake") is not None and shutil.which("lean") is not None


@cache
def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


@cache
def keycloak_available() -> bool:
    """The development Keycloak of deploy/keycloak (docs/adr/0010)."""
    import httpx

    try:
        r = httpx.get("http://localhost:8080/realms/dpc/.well-known/openid-configuration",
                      timeout=3)
    except httpx.HTTPError:
        return False
    return r.status_code == 200


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "keycloak" in item.keywords and not keycloak_available():
            item.add_marker(pytest.mark.skip(reason="development Keycloak not running"))
        if "lean" in item.keywords and not has_lean():
            item.add_marker(pytest.mark.skip(reason="no Lean toolchain (elan) on PATH"))
        if "docker" in item.keywords and not docker_available():
            item.add_marker(pytest.mark.skip(reason="Docker daemon not available"))


@pytest.fixture(scope="session")
def basic_core() -> Analysis:
    return Analysis.load(DATA / "basic" / "core.jsonl")


@pytest.fixture(scope="session")
def basic_metadata() -> Analysis:
    return Analysis.load(DATA / "basic" / "metadata.jsonl")


@pytest.fixture(scope="session")
def basic(basic_core: Analysis, basic_metadata: Analysis) -> Analysis:
    return merge(basic_core, basic_metadata)


@pytest.fixture(scope="session")
def host_executor() -> HostExecutor:
    # The analyzer build is cached across runs (it takes ~2 min the first time).
    return HostExecutor(trusted=True, cache_dir=CACHE)


def copy_fixture(name: str, dest: Path) -> Path:
    target = dest / name
    shutil.copytree(FIXTURES / name, target, ignore=shutil.ignore_patterns(".lake"))
    return target


def git(*args: str, cwd: Path) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "dpc", "GIT_AUTHOR_EMAIL": "dpc@example.invalid",
           "GIT_COMMITTER_NAME": "dpc", "GIT_COMMITTER_EMAIL": "dpc@example.invalid"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


def make_git_repo(tmp_path: Path, fixture: str) -> tuple[Path, str]:
    """A local git repository containing a fixture; returns (path, commit)."""
    repo = copy_fixture(fixture, tmp_path / "upstream")
    git("init", "--quiet", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "--quiet", "-m", "fixture", cwd=repo)
    return repo, git("rev-parse", "HEAD", cwd=repo)
