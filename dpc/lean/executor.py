"""Executors that build and analyse Lake projects.

* :class:`HostExecutor` runs Lean directly on this machine. **Only for trusted
  input** (the project's own fixtures, development); it refuses to start unless
  constructed with ``trusted=True``.
* :class:`DockerExecutor` is the sandbox for foreign repositories (SR-20, C7):
  no network, read-only source tree, CPU/RAM/process/time limits, all
  capabilities dropped, unprivileged user, container removed afterwards.

Both expose the same two operations, so the ingest pipeline does not care
where Lean runs (docs/adr/0003: jobs are pure functions of their inputs).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from dpc.lean.project import lean_path, read_manifest, read_toolchain, runtime_env, toolchain_slug

Mode = Literal["core", "metadata"]

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_SRC = REPO_ROOT / "lean" / "analyzer"
DOCKERFILE = REPO_ROOT / "sandbox" / "lean.Dockerfile"


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


class LeanExecutor(Protocol):
    name: str

    def build(self, project: Path, targets: Sequence[str]) -> RunResult: ...

    def analyze(
        self, project: Path, *, root: str, imports: Sequence[str], mode: Mode, out: Path
    ) -> RunResult: ...


def analyzer_source_hash() -> str:
    """Content hash of the analyzer sources; part of every cache key."""
    digest = hashlib.sha256()
    for path in sorted(ANALYZER_SRC.rglob("*")):
        rel = path.relative_to(ANALYZER_SRC)
        if ".lake" in rel.parts or not path.is_file() or rel.name == "lean-toolchain":
            continue
        digest.update(rel.as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _analyzer_args(root: str, imports: Sequence[str], mode: Mode, out: str) -> list[str]:
    args = ["--root", root]
    for module in imports:
        args += ["--import", module]
    if mode == "metadata":
        args.append("--metadata")
    return [*args, "--out", out]


def _run(argv: Sequence[str], *, cwd: Path | None, env: dict[str, str] | None,
         timeout_s: float, on_timeout: Sequence[str] | None = None) -> RunResult:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            list(argv), cwd=cwd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        if on_timeout:
            subprocess.run(list(on_timeout), capture_output=True, check=False)
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        err = exc.stderr if isinstance(exc.stderr, str) else ""
        return RunResult(tuple(argv), -1, out, err, time.monotonic() - start, timed_out=True)
    return RunResult(tuple(argv), proc.returncode, proc.stdout, proc.stderr,
                     time.monotonic() - start)


# ---------------------------------------------------------------------- host
class HostExecutor:
    """Runs Lean on the host. Trusted input only (see module docstring)."""

    name = "host"

    def __init__(self, *, trusted: bool, cache_dir: Path, timeout_s: float = 3600.0) -> None:
        if not trusted:
            raise PermissionError(
                "HostExecutor runs foreign code without isolation; pass trusted=True only "
                "for your own fixtures, otherwise use DockerExecutor"
            )
        self.cache_dir = cache_dir
        self.timeout_s = timeout_s

    def analyzer_exe(self, toolchain: str) -> Path:
        """Analyzer built for exactly ``toolchain`` (olean formats are version-bound)."""
        key = f"{toolchain_slug(toolchain)}-{analyzer_source_hash()[:12]}"
        target = self.cache_dir / "analyzer" / key
        exe = target / ".lake" / "build" / "bin" / (
            "dpc-analyze.exe" if sys.platform == "win32" else "dpc-analyze"
        )
        if exe.is_file():
            return exe
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ANALYZER_SRC, target, ignore=shutil.ignore_patterns(".lake"))
        (target / "lean-toolchain").write_text(toolchain + "\n", encoding="utf-8")
        result = _run(["lake", "build"], cwd=target, env=None, timeout_s=self.timeout_s)
        if not result.ok or not exe.is_file():
            raise RuntimeError(f"building the analyzer for {toolchain} failed:\n{result.output}")
        return exe

    def build(self, project: Path, targets: Sequence[str]) -> RunResult:
        return _run(["lake", "build", *targets], cwd=project, env=None, timeout_s=self.timeout_s)

    def analyze(
        self, project: Path, *, root: str, imports: Sequence[str], mode: Mode, out: Path
    ) -> RunResult:
        exe = self.analyzer_exe(read_toolchain(project))
        out.parent.mkdir(parents=True, exist_ok=True)
        sysroot = _run(["lean", "--print-prefix"], cwd=project, env=None, timeout_s=60)
        if not sysroot.ok:
            return sysroot
        env = runtime_env(Path(sysroot.stdout.strip()), lean_path(project, read_manifest(project)))
        argv = [str(exe), *_analyzer_args(root, imports, mode, str(out))]
        return _run(argv, cwd=project, env=env, timeout_s=self.timeout_s)


# -------------------------------------------------------------------- docker
@dataclass(frozen=True)
class Limits:
    cpus: float = 2.0
    memory: str = "8g"
    pids: int = 1024
    tmp_size: str = "2g"
    timeout_s: float = 3600.0


@dataclass(frozen=True)
class Mount:
    """A bind mount (host path) or a named volume, optionally a sub-directory of it."""

    source: Path | str
    target: str
    read_only: bool = True
    volume: bool = False
    subpath: str | None = None

    def arg(self) -> str:
        kind = "volume" if self.volume else "bind"
        spec = f"type={kind},source={self.source},target={self.target}"
        if self.subpath:
            if not self.volume:
                raise ValueError("subpath is only supported for volumes")
            spec += f",volume-subpath={self.subpath}"
        return spec + (",readonly" if self.read_only else "")


@dataclass
class DockerExecutor:
    """Sandbox executor (SR-20). Images are built per toolchain in a trusted step."""

    limits: Limits = field(default_factory=Limits)
    image_repo: str = "dpc-lean"
    docker: str = "docker"
    name: str = "docker"

    WORK = PurePosixPath("/work")

    def image_for(self, toolchain: str) -> str:
        tag = re.sub(r"[^A-Za-z0-9_.-]", "_", toolchain)
        return f"{self.image_repo}:{tag}-{analyzer_source_hash()[:12]}"

    def ensure_image(self, toolchain: str) -> str:
        """Build the sandbox image if missing. Trusted step; needs network."""
        image = self.image_for(toolchain)
        probe = _run([self.docker, "image", "inspect", image], cwd=None, env=None, timeout_s=60)
        if probe.ok:
            return image
        argv = [
            self.docker, "build", "--file", str(DOCKERFILE),
            "--build-arg", f"LEAN_TOOLCHAIN={toolchain}", "--tag", image, str(REPO_ROOT),
        ]
        result = _run(argv, cwd=REPO_ROOT, env=None, timeout_s=3600)
        if not result.ok:
            raise RuntimeError(f"building sandbox image {image} failed:\n{result.output}")
        return image

    def run_argv(
        self, image: str, command: Sequence[str], *, mounts: Sequence[Mount],
        env: dict[str, str] | None = None, container: str, network: bool = False,
    ) -> list[str]:
        """The full `docker run` command line. Pure, so the isolation flags can be
        inspected in tests without Docker (SR-20, verification by inspection).

        ``network=True`` is reserved for *trusted* steps (fetching sources and the
        Mathlib cache); everything touching foreign code runs without network."""
        lim = self.limits
        argv = [
            self.docker, "run", "--rm", "--name", container,
            "--network", "bridge" if network else "none",
            "--read-only",
            "--tmpfs", f"/tmp:rw,nosuid,size={lim.tmp_size}",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "1000:1000",
            "--cpus", str(lim.cpus),
            "--memory", lim.memory, "--memory-swap", lim.memory,
            "--pids-limit", str(lim.pids),
            "--workdir", str(self.WORK),
        ]
        for mount in mounts:
            argv += ["--mount", mount.arg()]
        for key, value in sorted((env or {}).items()):
            argv += ["--env", f"{key}={value}"]
        return [*argv, image, *command]

    def _exec(self, image: str, command: Sequence[str], mounts: Sequence[Mount],
              env: dict[str, str] | None = None, *, network: bool = False) -> RunResult:
        container = f"dpc-{uuid.uuid4().hex[:12]}"
        argv = self.run_argv(image, command, mounts=mounts, env=env, container=container,
                             network=network)
        return _run(argv, cwd=None, env=None, timeout_s=self.limits.timeout_s,
                    on_timeout=[self.docker, "kill", container])

    OUT = PurePosixPath("/out")

    def build_mounts(self, project: Path) -> list[Mount]:
        """Sources read-only; only ``.lake`` (build outputs) is writable, and the
        fetched dependencies inside it — including Mathlib's oleans — stay
        read-only so build-time code cannot tamper with them."""
        lake = project / ".lake"
        mounts = [
            Mount(project, str(self.WORK)),
            Mount(lake, str(self.WORK / ".lake"), read_only=False),
        ]
        packages = lake / "packages"
        if packages.is_dir():
            mounts.append(Mount(packages, str(self.WORK / ".lake" / "packages")))
        return mounts

    def analyze_mounts(self, project: Path, out_dir: Path) -> list[Mount]:
        """Everything read-only except the directory receiving the JSON Lines."""
        return [Mount(project, str(self.WORK)), Mount(out_dir, str(self.OUT), read_only=False)]

    def build(self, project: Path, targets: Sequence[str]) -> RunResult:
        image = self.ensure_image(read_toolchain(project))
        (project / ".lake" / "build").mkdir(parents=True, exist_ok=True)
        return self._exec(image, ["lake", "build", *targets], self.build_mounts(project))

    def analyze(
        self, project: Path, *, root: str, imports: Sequence[str], mode: Mode, out: Path
    ) -> RunResult:
        image = self.ensure_image(read_toolchain(project))
        out.parent.mkdir(parents=True, exist_ok=True)
        search = lean_path(self.WORK, read_manifest(project))
        command = ["/opt/dpc/analyze.sh",
                   *_analyzer_args(root, imports, mode, str(self.OUT / out.name))]
        # The container is Linux: ':' separates search path entries.
        return self._exec(image, command, self.analyze_mounts(project, out.parent),
                          env={"LEAN_PATH": ":".join(search)})
