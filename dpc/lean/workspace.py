"""Submission workspace inside a Docker named volume.

Why a volume instead of a host directory:

* Foreign repositories may contain file names the host cannot represent
  (observed: checking out ``openai/math`` on Windows fails).
* Bind mounts from the host are slow for Mathlib-sized trees (several GB,
  >100k files); a volume lives on the Linux side.
* The volume is the content-addressed artifact of docs/adr/0003 and can be
  reused for later jobs on the same commit.

Steps and their trust level (docs/adr/0005):

1. ``fetch``        trusted, network: plain ``git`` in a git-only image.
2. ``fetch_cache``  trusted, network: Mathlib's own cache tool, run with Mathlib
                    as the Lake root, so the submission's lakefile never runs.
3. ``build``        untrusted, no network: sources read-only, hardened packages
                    read-only, only build outputs writable.
4. ``analyze``      untrusted, no network: everything read-only except the
                    output directory.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dpc.audit.canonical import sha256_hex
from dpc.ingest.fetch import FetchError
from dpc.lean.executor import (
    REPO_ROOT,
    DockerExecutor,
    Mode,
    Mount,
    RunResult,
    _analyzer_args,
    _run,
)
from dpc.lean.project import COMMIT_RE, Manifest, Package, ProjectError, lean_path

FETCH_DOCKERFILE = REPO_ROOT / "sandbox" / "fetch.Dockerfile"
FETCH_IMAGE = "dpc-fetch:1"

URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._/-]+$")
NAME_RE = re.compile(r"^[A-Za-z0-9_.«»-]+$")

#: Hardened packages and the only source they are accepted from.
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


def validate_packages(manifest: Manifest) -> None:
    """Reject anything that could not be fetched safely or would fake hardening."""
    for pkg in manifest.packages:
        if pkg.type != "git" or not pkg.url:
            raise FetchError(f"package {pkg.name!r}: only git dependencies are supported")
        if not NAME_RE.match(pkg.name):
            raise FetchError(f"package name {pkg.name!r} is not allowed")
        if not URL_RE.match(pkg.url):
            raise FetchError(f"package {pkg.name!r}: unsupported URL {pkg.url!r}")
        if not pkg.rev or not COMMIT_RE.match(pkg.rev):
            raise FetchError(f"package {pkg.name!r} is not pinned to a commit")
        if pkg.name in OFFICIAL_PACKAGES and not is_official(pkg):
            raise FetchError(
                f"package {pkg.name!r} claims to be a hardened library but comes from "
                f"{pkg.url!r} instead of {OFFICIAL_PACKAGES[pkg.name]!r}"
            )


def _clone_script(url: str, rev: str, dest: PurePosixPath) -> str:
    q = shlex.quote
    return (
        f"mkdir -p {q(str(dest))} && cd {q(str(dest))} && git init --quiet && "
        f"git remote add origin {q(url)} && "
        f"(git fetch --quiet --depth 1 origin {q(rev)} || git fetch --quiet origin) && "
        f"git -c advice.detachedHead=false checkout --quiet --detach {q(rev)} && "
        f'test "$(git rev-parse HEAD)" = {q(rev)}'
    )


@dataclass(frozen=True)
class IntegrityReport:
    changed: tuple[str, ...]  # existed before, different or missing afterwards
    added: tuple[str, ...]  # new sources/oleans inside hardened packages

    @property
    def ok(self) -> bool:
        return not self.changed and not self.added


def compare_digests(before: Mapping[str, str], after: Mapping[str, str]) -> IntegrityReport:
    """Any change to a hardened source or `.olean` is blocking: either the build
    tampered with it, or it rebuilt a hardened module outside the trusted step."""
    changed = tuple(sorted(p for p, h in before.items() if after.get(p) != h))
    added = tuple(sorted(set(after) - set(before)))
    return IntegrityReport(changed, added)


@dataclass(frozen=True)
class Fetched:
    toolchain: str
    manifest: Manifest
    manifest_sha256: str
    reused: bool


@dataclass
class VolumeWorkspace:
    executor: DockerExecutor
    volume: str
    project_dir: str = ""

    WS = PurePosixPath("/ws")

    # ------------------------------------------------------------- helpers
    @property
    def repo(self) -> PurePosixPath:
        return self.WS / "repo"

    @property
    def project(self) -> PurePosixPath:
        return self.repo / self.project_dir if self.project_dir else self.repo

    def _sub(self, path: PurePosixPath) -> str:
        """Path inside the volume, relative to its root (for volume-subpath)."""
        return str(path.relative_to(self.WS))

    def _docker(self, *args: str, timeout_s: float = 600) -> RunResult:
        return _run([self.executor.docker, *args], cwd=None, env=None, timeout_s=timeout_s)

    def _script(self, image: str, script: str, *, network: bool,
                env: dict[str, str] | None = None) -> RunResult:
        mounts = [Mount(self.volume, str(self.WS), read_only=False, volume=True)]
        return self.executor._exec(image, ["sh", "-c", script], mounts, env, network=network)

    def _require(self, result: RunResult, what: str) -> RunResult:
        if not result.ok:
            raise FetchError(f"{what} failed:\n{result.output.strip()[-3000:]}")
        return result

    def ensure_fetch_image(self) -> str:
        if not self._docker("image", "inspect", FETCH_IMAGE).ok:
            built = self._docker("build", "--file", str(FETCH_DOCKERFILE), "--tag", FETCH_IMAGE,
                                 str(REPO_ROOT / "sandbox"), timeout_s=1800)
            self._require(built, "building the fetch image")
        return FETCH_IMAGE

    def create(self) -> None:
        self._require(self._docker("volume", "create", self.volume), "creating the volume")

    def remove(self) -> None:
        self._docker("volume", "rm", "--force", self.volume)

    def read_text(self, path: PurePosixPath, image: str) -> str:
        return self._require(
            self._script(image, f"cat {shlex.quote(str(path))}", network=False), f"reading {path}"
        ).stdout

    # ------------------------------------------------------- 1. fetch (trusted)
    MARKER = PurePosixPath("/ws/.dpc-fetched")

    def fetch(self, repo_url: str, commit: str) -> Fetched:
        """Clone the repository and all dependencies at their pinned commits.

        Idempotent: a volume that already holds this commit is reused."""
        if not URL_RE.match(repo_url):
            raise FetchError(f"unsupported repository URL {repo_url!r}")
        if not COMMIT_RE.match(commit):
            raise FetchError("a full 40-character commit hash is required")
        image = self.ensure_fetch_image()
        probe = self._script(image, f"cat {self.MARKER}", network=False)
        reused = probe.ok and probe.stdout.strip() == commit
        if not reused:
            self._require(self._script(image, _clone_script(repo_url, commit, self.repo),
                                       network=True), "cloning the repository")
        toolchain = self.read_text(self.project / "lean-toolchain", image).strip()
        try:
            raw = self.read_text(self.project / "lake-manifest.json", image)
        except FetchError as exc:
            raise ProjectError("missing lake-manifest.json (SR-01)") from exc
        manifest = Manifest.model_validate(json.loads(raw))
        validate_packages(manifest)
        if not reused:
            packages = self.project / manifest.packages_dir
            script = " && ".join(
                _clone_script(p.url or "", p.rev or "", packages / p.name)
                for p in manifest.packages
            ) or "true"
            self._require(self._script(image, script, network=True), "cloning dependencies")
            self._require(self._script(image, f"echo {commit} > {self.MARKER}", network=False),
                          "writing the fetch marker")
        return Fetched(toolchain, manifest, sha256_hex(raw.encode("utf-8")), reused)

    # ------------------------------------------------- 2. mathlib cache (trusted)
    def fetch_cache(self, image: str, manifest: Manifest) -> RunResult | None:
        """Download Mathlib's prebuilt .olean files without running the submission.

        Mathlib becomes the Lake root; its own dependencies are found through a
        symlink to the submission's packages directory (same names, same pinned
        revisions). Only code from official, hardened packages runs here."""
        mathlib = next((p for p in manifest.packages if p.name == "mathlib"), None)
        if mathlib is None:
            return None
        if not is_official(mathlib):  # validate_packages already ensures this
            raise FetchError("refusing to run the cache tool of an unofficial mathlib")
        root = self.project / manifest.packages_dir / "mathlib"
        cache = self.WS / ".cache"
        script = (
            f"cd {shlex.quote(str(root))} && mkdir -p .lake && "
            "rm -rf .lake/packages && ln -s ../.. .lake/packages && "
            "lake exe cache get"
        )
        env = {"XDG_CACHE_HOME": str(cache), "MATHLIB_CACHE_DIR": str(cache / "mathlib"),
               "HOME": "/tmp"}
        return self._script(image, script, network=True, env=env)

    def package_heads(self, image: str, manifest: Manifest) -> dict[str, str]:
        """Current commit of every dependency (to detect tampering by the cache step)."""
        packages = self.project / manifest.packages_dir
        script = "; ".join(
            f"printf '%s %s\\n' {shlex.quote(p.name)} "
            f"\"$(git -C {shlex.quote(str(packages / p.name))} rev-parse HEAD)\""
            for p in manifest.packages
        ) or "true"
        out = self._require(self._script(image, script, network=False), "reading revisions")
        heads = dict(line.split(" ", 1) for line in out.stdout.splitlines() if " " in line)
        return {k: v.strip() for k, v in heads.items()}

    # ------------------------------------------- integrity of the hardened set
    DIGEST_PATTERNS = ("*.lean", "*.olean", "*.olean.*", "*.ilean", "*.ir")

    def digest_hardened(self, image: str, manifest: Manifest) -> dict[str, str]:
        """SHA-256 of every source and build artifact of the official packages.

        Taken right after the trusted cache step and again after the untrusted
        build. The build cannot be denied write access to these packages (Lake
        caches input hashes next to source files, e.g. in ProofWidgets), so
        tampering is *detected* instead: see :func:`compare_digests`."""
        packages = self.project / manifest.packages_dir
        dirs = [shlex.quote(str(packages / p.name)) for p in manifest.packages if is_official(p)]
        if not dirs:
            return {}
        names = " -o ".join(f"-name {shlex.quote(p)}" for p in self.DIGEST_PATTERNS)
        script = (f"find {' '.join(dirs)} -type f \\( {names} \\) -print0 "
                  "| xargs -0 -r -P 8 -n 512 sha256sum")
        out = self._require(self._script(image, script, network=False), "hashing hardened files")
        digests: dict[str, str] = {}
        for line in out.stdout.splitlines():
            digest, _, path = line.partition("  ")
            if path:
                digests[path] = digest
        return digests

    # ----------------------------------------------- 3./4. build and analyse
    def build_mounts(self, manifest: Manifest) -> list[Mount]:
        """Sources read-only, ``.lake`` (build outputs and dependencies) writable.
        Changes to hardened packages are detected via :meth:`digest_hardened`."""
        work = self.executor.WORK
        return [
            Mount(self.volume, str(work), volume=True, subpath=self._sub(self.project)),
            Mount(self.volume, str(work / ".lake"), read_only=False, volume=True,
                  subpath=self._sub(self.project / ".lake")),
        ]

    def build(self, image: str, manifest: Manifest, targets: Sequence[str]) -> RunResult:
        env = {"HOME": "/tmp", "XDG_CACHE_HOME": "/tmp/cache"}
        return self.executor._exec(image, ["lake", "build", *targets],
                                   self.build_mounts(manifest), env)

    def analyze(self, image: str, manifest: Manifest, *, root: str, imports: Sequence[str],
                mode: Mode, out: Path) -> RunResult:
        out.parent.mkdir(parents=True, exist_ok=True)
        work, out_dir = self.executor.WORK, self.executor.OUT
        mounts = [
            Mount(self.volume, str(work), volume=True, subpath=self._sub(self.project)),
            Mount(out.parent, str(out_dir), read_only=False),
        ]
        command = ["/opt/dpc/analyze.sh",
                   *_analyzer_args(root, imports, mode, str(out_dir / out.name))]
        env = {"LEAN_PATH": ":".join(lean_path(work, manifest)), "HOME": "/tmp"}
        return self.executor._exec(image, command, mounts, env)

    # ----------------------------------------------------- hardening evidence
    def official_modules(self, image: str, manifest: Manifest) -> dict[str, frozenset[str]]:
        """Module names actually shipped by the toolchain and by each official
        package — evidence for `dpc.analysis.hardening.unverified_hardened_modules`."""
        packages = self.project / manifest.packages_dir
        parts = ['echo "@core"; cd "$(lean --print-prefix)/lib/lean" && find . -name "*.olean"']
        for pkg in manifest.packages:
            if is_official(pkg):
                parts.append(f"echo @{shlex.quote(pkg.name)}; "
                             f"git -C {shlex.quote(str(packages / pkg.name))} ls-files '*.lean'")
        out = self._require(self._script(image, "; ".join(parts), network=False),
                            "listing official modules")
        result: dict[str, set[str]] = {}
        current = ""
        for line in out.stdout.splitlines():
            if line.startswith("@"):
                current = line[1:]
                result[current] = set()
                continue
            path = line.removeprefix("./")
            for suffix in (".olean", ".lean"):
                if path.endswith(suffix):
                    result[current].add(path.removesuffix(suffix).replace("/", "."))
        return {k: frozenset(v) for k, v in result.items()}
