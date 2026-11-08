"""Trusted fetch step: repository and dependencies at pinned revisions.

This step needs network access and therefore runs *outside* the sandbox. It
must not execute any code from the submission. In particular it never invokes
``lake``: Lake would evaluate the repository's ``lakefile.lean`` — foreign code
— with network access. Instead, dependencies are cloned with plain ``git``
exactly at the revisions recorded in ``lake-manifest.json`` (docs/adr/0005).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from dpc.lean.project import COMMIT_RE, Manifest


class FetchError(RuntimeError):
    """A repository or dependency could not be fetched at its pinned revision."""


def _git(*args: str, cwd: Path | None = None) -> str:
    # Hooks are disabled defensively; a fresh clone has none, but a reused
    # directory could.
    argv = ["git", "-c", "core.hooksPath=/dev/null", "-c", "advice.detachedHead=false", *args]
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise FetchError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def clone_at_commit(url: str, commit: str, dest: Path) -> None:
    """Check out ``url`` at exactly ``commit`` (full hash) into ``dest``.

    Tries a shallow fetch of the single commit first and falls back to a full
    clone for servers that do not allow fetching by hash.
    """
    if not COMMIT_RE.match(commit):
        raise FetchError(f"{url}: a full 40-character commit hash is required, got {commit!r}")
    if dest.exists() and any(dest.iterdir()):
        raise FetchError(f"{dest} already exists and is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    _git("init", "--quiet", cwd=dest)
    _git("remote", "add", "origin", url, cwd=dest)
    try:
        _git("fetch", "--quiet", "--depth", "1", "origin", commit, cwd=dest)
    except FetchError:
        _git("fetch", "--quiet", "origin", cwd=dest)
    _git("checkout", "--quiet", "--detach", commit, cwd=dest)
    head = _git("rev-parse", "HEAD", cwd=dest).strip()
    if head != commit:
        raise FetchError(f"{url}: checked out {head}, expected {commit}")


@dataclass(frozen=True)
class FetchedPackage:
    name: str
    url: str
    rev: str


def fetch_dependencies(project: Path, manifest: Manifest) -> list[FetchedPackage]:
    """Clone every manifest package at its pinned revision (SR-01)."""
    fetched: list[FetchedPackage] = []
    for pkg in manifest.packages:
        if pkg.type != "git" or not pkg.url:
            raise FetchError(
                f"package {pkg.name!r}: only git dependencies are supported (got {pkg.type!r})"
            )
        if not pkg.rev or not COMMIT_RE.match(pkg.rev):
            raise FetchError(f"package {pkg.name!r} is not pinned to a commit")
        clone_at_commit(pkg.url, pkg.rev, project / manifest.packages_dir / pkg.name)
        fetched.append(FetchedPackage(pkg.name, pkg.url, pkg.rev))
    return fetched
