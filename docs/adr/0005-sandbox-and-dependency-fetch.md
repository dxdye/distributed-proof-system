# ADR 0005 — Sandbox and dependency fetch

Status: accepted (2026-11-08) · implemented in `dpc/ingest`, `dpc/lean/executor.py`,
`dpc/lean/workspace.py`, `sandbox/`

## Context

Lean runs code during the build (macros, `initialize`, `#eval`), and Lake runs
`lakefile.lean` — also code. SR-20 demands isolation without network. But
dependencies, including Mathlib's prebuilt `.olean` cache, must be downloaded.

The pipeline must work for **any** Lean 4 project: with or without Mathlib,
with arbitrary further dependencies, on any toolchain. Nothing below is
specific to a particular case study.

## Decision

**Split trusted and untrusted steps.**

1. *Trusted fetch (network, git only):* clone the repository at the full commit
   hash and every dependency from `lake-manifest.json` at its pinned revision,
   using a git-only image. Lake is **not** invoked, because it would evaluate
   the submission's lakefile with network access. A missing manifest, an
   unpinned dependency, a non-https URL, or a *hardened* package (Mathlib,
   Batteries, Aesop, …) from anywhere but its official repository rejects the
   submission.
2. *Trusted cache fetch (network, only if Mathlib is a dependency):* Mathlib
   becomes the Lake root; its own dependencies are reached through a symlink to
   the submission's packages directory (same names, same pinned revisions).
   `lake exe cache get` then runs only code from official packages. Afterwards
   all dependencies are checked to still be at their pinned revisions.
3. *Snapshot:* SHA-256 of every source, build artifact and configuration file
   of the hardened packages (`*.lean`, `*.olean*`, `*.ilean`, `*.ir`,
   `lakefile.toml`, `lake-manifest.json`, `lean-toolchain`). Lake's own
   bookkeeping (`*.hash`, `*.trace`) is excluded: the first Navier–Stokes run
   showed Lake legitimately rewriting an `.olean.hash` while the `.olean` stayed
   identical. The snapshot is stored in the volume *outside* every mount used
   by untrusted steps.
4. *Untrusted build (sandbox, no network):* `docker run` with `--network none`,
   read-only root filesystem, read-only source tree, only `.lake/` writable,
   all capabilities dropped, `no-new-privileges`, unprivileged user, limits for
   CPU, memory, processes and wall time, container removed afterwards.
5. *Verify:* the snapshot is recomputed. Any changed, removed or added source or
   `.olean` in a hardened package is a blocking finding — either the build
   tampered with it, or a hardened module was rebuilt outside the trusted step.
6. *Untrusted analysis (sandbox, no network):* everything read-only except the
   output directory; core and metadata runs are cross-checked (ADR 0004); every
   module marked hardened must be shipped by the toolchain or an official
   package (`dpc/analysis/hardening.py`).

**No trusted step after foreign code.** A marker is set before the first
untrusted step. A volume that has run foreign code never runs a trusted step
again (network, Lake on hardened packages): an untrusted build could have
rewritten a hardened package's lakefile, which the next cache fetch would
execute with network access. A reused volume is first compared with its stored
snapshot; a mismatch, or a marker without snapshot, means: discard the volume
and start from scratch.

**Dependency patches.** Some formalizations patch third-party dependencies to
make them compile with their toolchain (observed: `openai/math` ships 23
`patches/<package>-lean4341.patch` files; its lakefile applies 11 of them at
configuration time, the rest via `lake update`). The pinned revisions alone are
then not buildable. A submission may declare a patch directory; every
`<package>-*.patch` is applied with `git apply` in the trusted fetch step
(patch files are data — no repository code runs), recorded with its SHA-256 in
the audit log, and refused for hardened packages. Patched code is no longer the
upstream revision: the patches belong to what is reviewed.

**Where the files live.** Real submissions are processed in a Docker named
volume (`VolumeWorkspace`), not on the host: repositories may contain file
names the host cannot represent (observed: `openai/math` on Windows), and bind
mounts are slow for Mathlib-sized trees. Small trusted fixtures can still use
host directories.

**Why detection instead of read-only mounts for hardened packages.** The first
attempt mounted them read-only. Every Mathlib project failed: Lake caches input
hashes next to source files (e.g. `ProofWidgets/widget/package-lock.json.hash`)
even when everything is taken from the cache. Steps 3 and 5 give the same
guarantee — tampering cannot reach the analysis — without breaking builds.

Images are built per toolchain in a trusted step and contain the analyzer
compiled for that toolchain. The red-team fixture (`lean/fixtures/redteam`)
checks that build-time code can neither write into the source tree or the
system nor reach the network.

`HostExecutor` runs Lean without isolation and refuses to start unless
explicitly told the input is trusted (own fixtures, development).

## Open points

- ~~**Forged `.olean` files of the submission itself.**~~ Resolved by
  [ADR 0009](0009-kernel-replay.md): every module that is not loaded from the
  toolchain or an official package is replayed through the kernel. ADR 0009 also
  closes a gap in steps 3/5. Modules used to be resolved through a search path
  that began with the submission's own build directory, so a forged copy of
  `Mathlib` placed there would have been loaded instead of the verified one.
- **Other prebuilt caches.** Only Mathlib's cache is fetched. Projects with
  further large dependencies build them in the sandbox, which is slow but safe.
- **Artifact store.** Volumes are named after commit and origin and reused by
  later runs; garbage collection and sharing Mathlib between volumes are open
  (ADR 0003).
