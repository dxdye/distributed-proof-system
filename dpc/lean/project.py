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

    @property
    def dir_name(self) -> str:
        """Directory below the packages dir. Manifests store Lean-escaped names
        (`«tate-curves-theta»`), Lake's directories use the plain name."""
        name = self.name
        if name.startswith("«") and name.endswith("»"):
            name = name[1:-1]
        return name


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


#: Hardened packages and the only source they are accepted from (docs/adr/0005).
OFFICIAL_PACKAGES: Mapping[str, str] = {
    "mathlib": "https://github.com/leanprover-community/mathlib4",
    "batteries": "https://github.com/leanprover-community/batteries",
    "aesop": "https://github.com/leanprover-community/aesop",
    "Qq": "https://github.com/leanprover-community/quote4",
    "proofwidgets": "https://github.com/leanprover-community/ProofWidgets4",
    "importGraph": "https://github.com/leanprover-community/import-graph",
    "LeanSearchClient": "https://github.com/leanprover-community/LeanSearchClient",
    "plausible": "https://github.com/leanprover-community/plausible",
}


def normalize_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git")


def is_official(pkg: Package) -> bool:
    return pkg.url is not None and OFFICIAL_PACKAGES.get(pkg.name) == normalize_url(pkg.url)


def _package_lib(root: PurePosixPath | Path, manifest: Manifest,
                 pkg: Package) -> PurePosixPath | Path:
    base = root / manifest.packages_dir / pkg.dir_name
    if pkg.sub_dir:
        base = base / pkg.sub_dir
    return base / ".lake" / "build" / "lib" / "lean"


def trusted_lean_path(root: PurePosixPath | Path, manifest: Manifest) -> list[str]:
    """Build directories of the official packages. The pipeline verifies their
    files against the trusted snapshot (docs/adr/0005), so the analysis tools may
    trust modules loaded from there (docs/adr/0009)."""
    return [str(_package_lib(root, manifest, p)) for p in manifest.packages if is_official(p)]


def lean_path(root: PurePosixPath | Path, manifest: Manifest) -> list[str]:
    """Search path (LEAN_PATH) for the analysis tools.

    Lean loads a module from the *first* entry that contains a directory named
    after its root (`Mathlib/`, `Init/`, …). Trusted entries therefore come first:
    the toolchain's library (prepended by the tool runner and :func:`runtime_env`),
    then the official packages, then the project and its other dependencies.
    In the opposite order, a build could shadow `Mathlib` or `Init` with
    forged copies in its own build directory (docs/adr/0009)."""
    others = [str(root / ".lake" / "build" / "lib" / "lean")]
    others += [str(_package_lib(root, manifest, p))
               for p in manifest.packages if not is_official(p)]
    return [*trusted_lean_path(root, manifest), *others]


def runtime_env(
    sysroot: Path, search_path: Sequence[str], base: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Environment for running a Lean-linked executable on this host. The
    toolchain's library comes first on the search path (see :func:`lean_path`)."""
    env = dict(os.environ if base is None else base)
    env["LEAN_SYSROOT"] = str(sysroot)
    env["LEAN_PATH"] = os.pathsep.join([str(sysroot / "lib" / "lean"), *search_path])
    if sys.platform == "win32":
        env["PATH"] = str(sysroot / "bin") + os.pathsep + env.get("PATH", "")
    else:
        var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        env[var] = str(sysroot / "lib" / "lean") + os.pathsep + env.get(var, "")
    return env
