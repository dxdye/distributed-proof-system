"""Volume workspace: provenance of hardened packages, mounts (offline, no Docker)."""

from __future__ import annotations

import pytest

from dpc.analysis import Analysis
from dpc.analysis.hardening import unverified_hardened_modules
from dpc.ingest import FetchError, Submission
from dpc.ingest.volume import volume_name
from dpc.lean.executor import DockerExecutor, Mount
from dpc.lean.project import Manifest, Package
from dpc.lean.workspace import (
    VolumeWorkspace,
    compare_digests,
    is_official,
    validate_packages,
)

REV = "a" * 40
MATHLIB = Package(name="mathlib", type="git", rev=REV,
                  url="https://github.com/leanprover-community/mathlib4.git")
OTHER = Package(name="carleson", type="git", rev=REV,
                url="https://github.com/fpvandoorn/carleson.git")


@pytest.mark.req("SR-03", "SR-20")
def test_hardened_package_from_a_fork_is_rejected() -> None:
    fork = MATHLIB.model_copy(update={"url": "https://github.com/evil/mathlib4"})
    with pytest.raises(FetchError, match="claims to be a hardened library"):
        validate_packages(Manifest(packages=(fork,)))
    validate_packages(Manifest(packages=(MATHLIB, OTHER)))  # official + ordinary: fine


def test_escaped_package_names_map_to_plain_directories() -> None:
    """Manifests store `«tate-curves-theta»`; Lake's directory is `tate-curves-theta`
    (observed on openai/math)."""
    pkg = OTHER.model_copy(update={"name": "«tate-curves-theta»"})
    assert pkg.dir_name == "tate-curves-theta"
    assert OTHER.dir_name == "carleson"
    ws = VolumeWorkspace(DockerExecutor(), "vol")
    from dpc.lean.project import lean_path
    paths = lean_path(ws.project, Manifest(packages=(pkg,)))
    assert paths[1].endswith(".lake/packages/tate-curves-theta/.lake/build/lib/lean")


def test_url_normalisation() -> None:
    assert is_official(MATHLIB)
    assert is_official(MATHLIB.model_copy(update={"url": MATHLIB.url.removesuffix(".git") + "/"}))
    assert not is_official(OTHER)


@pytest.mark.parametrize("url", ["git@github.com:a/b.git", "https://x/a;rm -rf /", "file:///etc"])
def test_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(FetchError):
        validate_packages(Manifest(packages=(OTHER.model_copy(update={"url": url}),)))


@pytest.mark.req("SR-03")
def test_modules_posing_as_mathlib_are_reported(basic: Analysis) -> None:
    decls = dict(basic.decls)
    decls["Nat"] = decls["Nat"].model_copy(update={"module": "Mathlib.Evil"})
    analysis = Analysis(basic.header, decls)
    core_modules = {d.module for d in basic.decls.values() if d.hardened and d.module}
    official = {"core": frozenset(core_modules), "mathlib": frozenset({"Mathlib.Data.Nat"})}
    assert unverified_hardened_modules(basic, official) == []
    assert unverified_hardened_modules(analysis, official) == ["Mathlib.Evil"]


@pytest.mark.req("SR-20")
def test_volume_build_mounts_sources_read_only() -> None:
    ws = VolumeWorkspace(DockerExecutor(), "vol", project_dir="lean")
    mounts = {m.target: m for m in ws.build_mounts(Manifest(packages=(MATHLIB, OTHER)))}
    assert mounts["/work"].read_only and mounts["/work"].subpath == "repo/lean"
    assert not mounts["/work/.lake"].read_only
    arg = mounts["/work"].arg()
    assert "type=volume" in arg and "volume-subpath=repo/lean" in arg and "readonly" in arg


@pytest.mark.req("SR-20")
def test_tampering_with_hardened_files_is_detected() -> None:
    before = {"mathlib/Mathlib/A.lean": "1", "mathlib/.lake/build/lib/lean/Mathlib/A.olean": "2"}
    assert compare_digests(before, dict(before)).ok
    forged = {**before, "mathlib/.lake/build/lib/lean/Mathlib/A.olean": "evil"}
    report = compare_digests(before, forged)
    assert not report.ok and report.changed == ("mathlib/.lake/build/lib/lean/Mathlib/A.olean",)
    new_olean = "mathlib/.lake/build/lib/lean/Mathlib/B.olean"
    assert compare_digests(before, {**before, new_olean: "3"}).added == (new_olean,)
    deleted = {"mathlib/Mathlib/A.lean": "1"}
    assert not compare_digests(before, deleted).ok


def test_bind_mounts_cannot_have_subpaths() -> None:
    with pytest.raises(ValueError):
        Mount("/x", "/y", subpath="a").arg()


@pytest.mark.req("SR-20")
def test_network_only_on_request() -> None:
    executor = DockerExecutor()
    assert "none" in executor.run_argv("img", ["true"], mounts=[], container="c")
    trusted = executor.run_argv("img", ["true"], mounts=[], container="c", network=True)
    assert trusted[trusted.index("--network") + 1] == "bridge"


def test_volume_name_is_deterministic() -> None:
    sub = Submission(repo_url="https://github.com/a/b", commit=REV, root="A.b", root_module="A",
                     project_dir="lean")
    assert volume_name(sub) == volume_name(sub)
    assert volume_name(sub) != volume_name(sub.model_copy(update={"project_dir": ""}))
    with pytest.raises(ValueError):
        Submission(repo_url="x", commit=REV, root="A", root_module="A", project_dir="../etc")


def test_dependency_patches_map_to_packages_and_spare_hardened_ones() -> None:
    """Observed on openai/math: 24 compatibility patches for third-party packages."""
    from dpc.lean.workspace import map_patches

    schoen = OTHER.model_copy(update={"name": "«schoenflies-lean»"})
    schoen_core = OTHER.model_copy(update={"name": "schoenflies"})
    manifest = Manifest(packages=(MATHLIB, OTHER, schoen, schoen_core))
    listing = ("a" * 64 + " carleson-lean4341.patch\n"
               + "b" * 64 + " schoenflies-lean-lean4341.patch\n")
    patches = map_patches(listing, manifest)
    assert [(p.package, p.file) for p in patches] == [
        ("carleson", "carleson-lean4341.patch"),
        ("schoenflies-lean", "schoenflies-lean-lean4341.patch"),  # longest prefix wins
    ]
    with pytest.raises(FetchError, match="hardened"):
        map_patches("c" * 64 + " mathlib-fix.patch\n", manifest)
    with pytest.raises(FetchError, match="does not belong"):
        map_patches("d" * 64 + " unknown-x.patch\n", manifest)
    with pytest.raises(ValueError):
        Submission(repo_url="x", commit=REV, root="A", root_module="A", patch_dir="../evil")
