"""Several main theorems of one commit, ingested together (C-28, C-29).

Fetch, cache, snapshot and kernel replay depend only on the artifact, so they
run once; build and analysis run per main theorem. The volume is simulated:
the real steps run in Docker (tests marked ``docker`` elsewhere).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, ClassVar

import pytest

from dpc.analysis import Analysis
from dpc.audit import AuditLog
from dpc.ingest import Submission
from dpc.ingest import volume as vol
from dpc.ingest.pipeline import IngestError
from dpc.lean.executor import RunResult
from dpc.lean.project import Manifest
from dpc.lean.replay import SCHEMA, ReplayReport

from conftest import DATA

COMMIT = "c" * 40


def sub(root: str, module: str, **kw: Any) -> Submission:
    return Submission.model_validate({"repo_url": "https://x/math", "commit": COMMIT,
                                      "root": root, "root_module": module,
                                      "project_dir": "lean", **kw})


def ok(argv: str = "x", code: int = 0, out: str = "") -> RunResult:
    return RunResult((argv,), code, out, "", 1.0)


class FakeWorkspace:
    """A reused volume with a verified snapshot; records what runs."""

    calls: ClassVar[list[tuple[str, tuple[str, ...]]]] = []
    broken: ClassVar[set[str]] = set()

    def __init__(self, executor: Any, volume: str, project: str) -> None:
        self.volume = volume

    def create(self) -> None: ...

    def fetch(self, *_: Any) -> Any:
        class Fetched:
            manifest = Manifest(packages=())
            toolchain, manifest_sha256, reused, patches = "4.33.1", "m" * 64, True, ()
        return Fetched()

    def trusted_snapshot(self, image: str) -> dict[str, str]:
        return {"Mathlib/A.olean": "1"}

    def digest_hardened(self, image: str, manifest: Manifest, save: bool = False
                        ) -> dict[str, str]:
        return {"Mathlib/A.olean": "1"}

    def mark_untrusted(self, image: str) -> None: ...

    def build(self, image: str, manifest: Manifest, modules: list[str]) -> RunResult:
        self.calls.append(("build", tuple(modules)))
        return ok(code=1, out="error: does not build") if modules[0] in self.broken else ok()

    def replay(self, image: str, manifest: Manifest, *, roots: list[str], out: Path
               ) -> RunResult:
        self.calls.append(("replay", tuple(roots)))
        modules = sorted({d.module for d in Analysis.load(DATA / "basic" / "core.jsonl")
                          .decls.values() if d.module} | {"Elsewhere.Unrelated"})
        records = [{"kind": "header", "schema": SCHEMA, "toolchain": "4.33.1",
                    "roots": list(roots), "trusted": [], "core": "/t", "jobs": 1}]
        records += [{"kind": "module", "module": m, "origin": "replayed", "entry": "/w",
                     "constants": 2, "skipped": 0, "ok": True, "error": None} for m in modules]
        out.write_text("".join(json.dumps(r) + "\n" for r in records), "utf-8")
        return ok()

    def analyze(self, image: str, manifest: Manifest, *, root: str, imports: list[str],
                mode: str, out: Path) -> RunResult:
        self.calls.append(("analyze", (root, mode)))
        shutil.copy(DATA / "basic" / f"{mode}.jsonl", out)
        return ok()

    def official_modules(self, image: str, manifest: Manifest) -> dict[str, frozenset[str]]:
        return {}


class FakeExecutor:
    def ensure_image(self, toolchain: str) -> str:
        return "img"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> type[FakeWorkspace]:
    FakeWorkspace.calls, FakeWorkspace.broken = [], set()
    monkeypatch.setattr(vol, "VolumeWorkspace", FakeWorkspace)
    return FakeWorkspace


@pytest.mark.req("SR-01", "SR-02")
def test_a_batch_builds_each_theorem_and_replays_once(fake: type[FakeWorkspace],
                                                      tmp_path: Path) -> None:
    subs = [sub("Basic.main_theorem", "Basic"), sub("Other.main", "Other"),
            sub("Third.main", "Third")]
    fake.broken = {"Other"}
    names = {"Basic.main_theorem": "basic", "Other.main": "other", "Third.main": "third"}
    with AuditLog(tmp_path / "log.sqlite") as log:
        result = vol.ingest_batch_in_volume(subs, executor=FakeExecutor(),  # type: ignore[arg-type]
                                            log=log, out_root=tmp_path, name=names)
        kinds = [e.kind for e in log.entries()]
    # One that does not build holds up nobody; the replay runs once, over the rest.
    assert [c for c in fake.calls if c[0] == "build"] == [
        ("build", ("Basic",)), ("build", ("Other",)), ("build", ("Third",))]
    assert [c for c in fake.calls if c[0] == "replay"] == [("replay", ("Basic", "Third"))]
    assert set(result.results) == {"Basic.main_theorem", "Third.main"}
    assert result.failed["Other.main"].startswith("build failed")
    assert kinds.count("submission.received") == 3 and kinds.count("kernel.replayed") == 1
    assert kinds.count("hardened.reverified") == 1 and kinds.count("hardened.verified") == 1
    assert kinds.count("analysis.completed") == 2
    # Each theorem gets the part of the shared replay its declarations live in.
    mine = ReplayReport.load(tmp_path / "basic" / "analysis" / "replay.jsonl")
    assert "Elsewhere.Unrelated" not in {m.module for m in mine.modules}
    assert mine.header.roots == ("Basic", "Third")  # what the shared run covered
    assert mine.uncovered(Analysis.load(tmp_path / "basic" / "analysis" / "core.jsonl")) == []
    assert (tmp_path / "shared" / "replay.jsonl").is_file()


def test_a_batch_is_one_artifact(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="one repository, commit"):
        vol._same_artifact([sub("A.t", "A"), sub("B.t", "B", commit="d" * 40)])
    with pytest.raises(IngestError, match="listed twice"):
        vol._same_artifact([sub("A.t", "A"), sub("A.t", "A")])
