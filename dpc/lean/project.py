"""Reading a Lake project: toolchain, manifest, search paths."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dpc.audit.canonical import sha256_hex

TOOLCHAIN_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:[A-Za-z0-9_.+-]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ProjectError(ValueError):
    """The repository is not a well-formed, pinned Lake project."""


def read_toolchain(project: Path) -> str:
    path = project / "lean-toolchain"
    if not path.is_file():
        raise ProjectError("missing lean-toolchain (the toolchain must be pinned, SR-01)")
    text = path.read_text(encoding="utf-8").strip()
    if not TOOLCHAIN_RE.match(text):
        raise ProjectError(f"unsupported toolchain specification {text!r}")
    return text


def toolchain_slug(toolchain: str) -> str:
    """Directory name elan uses for a toolchain."""
    return toolchain.replace("/", "--").replace(":", "---")


class Package(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    name: str
    type: Literal["git", "path"]
    url: str | None = None
    rev: str | None = None
    input_rev: str | None = Field(default=None, alias="inputRev")
    sub_dir: str | None = Field(default=None, alias="subDir")
    dir: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    # Integer up to manifest format 7, semantic-version string ("1.2.0") since.
    version: int | str = 0
    name: str | None = None
    packages_dir: str = Field(default=".lake/packages", alias="packagesDir")
    packages: tuple[Package, ...] = ()


def read_manifest(project: Path, *, required: bool = False) -> Manifest:
    """The Lake manifest. ``required=True`` for submissions: without it the
    dependency versions are not pinned (SR-01), and Lake would try to write one
    into the read-only source tree."""
    path = project / "lake-manifest.json"
    if not path.is_file():
        if required:
            raise ProjectError("missing lake-manifest.json (dependencies must be pinned, SR-01)")
        return Manifest()
    return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def manifest_digest(project: Path) -> str:
    path = project / "lake-manifest.json"
    return sha256_hex(path.read_bytes() if path.is_file() else b"")


def lean_path(root: PurePosixPath | Path, manifest: Manifest) -> list[str]:
    """Build directories of the project and all its packages (for LEAN_PATH)."""
    pkg_root = root / manifest.packages_dir
    dirs = [root / ".lake" / "build" / "lib" / "lean"]
    for pkg in manifest.packages:
        base = pkg_root / pkg.name
        if pkg.sub_dir:
            base = base / pkg.sub_dir
        dirs.append(base / ".lake" / "build" / "lib" / "lean")
    return [str(d) for d in dirs]


def runtime_env(
    sysroot: Path, search_path: Sequence[str], base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Environment for running a Lean-linked executable on this host."""
    env = dict(os.environ if base is None else base)
    env["LEAN_SYSROOT"] = str(sysroot)
    env["LEAN_PATH"] = os.pathsep.join(search_path)
    if sys.platform == "win32":
        env["PATH"] = str(sysroot / "bin") + os.pathsep + env.get("PATH", "")
    else:
        var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        env[var] = str(sysroot / "lib" / "lean") + os.pathsep + env.get(var, "")
    return env
