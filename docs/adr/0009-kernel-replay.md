# ADR 0009 — Kernel replay and trust by location

Status: accepted (2026-11-13) · implemented in `lean/analyzer/ReplayMain.lean`,
`dpc/lean/replay.py`, `dpc/lean/project.py` (`lean_path`), `sandbox/run-tool.sh`,
`dpc/ingest`

## Context

The Lean kernel checks a declaration when it is added. When a module is
imported from its `.olean` file, nothing is checked again. The build of a
submission runs the submission's code (ADR 0005). That code can put
declarations into the `.olean` files of its own modules that the kernel never
saw: with `set_option debug.skipKernelTC`, with `addDecl` from meta code, or by
writing the files directly. The axiom check (SR-02) does not notice this. A
forged theorem is still a theorem and uses no axiom.

This was an open point of ADR 0005. The quasi-Riemann case study made it
urgent. There the statement is a single class-A ticket, and the result rests on
19 442 proof units that no human reviews completely.

A second gap turned up while implementing the replay. Lean resolves a module
by the **first** search path entry that contains a directory named after the
module's root (`Mathlib/`, `Init/`, …). `LEAN_PATH` comes before the
toolchain's library. Our `LEAN_PATH` listed the submission's own build
directory first, and the build can write there. A build could therefore leave
a forged copy of `Mathlib` or `Init` in its own build directory, and every
later tool would load it:
- The snapshot check (ADR 0005) saw nothing, because the official package
  stayed untouched.
- The provenance check saw nothing, because it compares module names.
- The analysis counted the forged modules as hardened. Their declarations
  dropped out of TCB_new, and nobody would have reviewed them.

## Decision

**Trusted entries first.** The search path of every analysis tool starts with
the toolchain's library, then the official packages, then the project and its
other dependencies (`lean_path`, `runtime_env`, `run-tool.sh`). A root name
that a trusted entry provides can no longer be shadowed.

**Trust by location, not by name.** A module counts as trusted only if it is
loaded from the toolchain's library or from the build directory of an official
package. The pipeline verifies the files there against the trusted snapshot
before any tool runs. Every other module is replayed. This holds regardless of
its name and of which package it belongs to.
- If the analysis counts a module as hardened (by name) and the module was
  loaded from an untrusted location, that is a blocking `finding.hardening`.
- If a trusted module imports a replayed one, that is an error, because the
  trusted base would then contain unchecked declarations.

**`dpc-replay`** (sandbox, no network, everything read-only except the output):
1. Loads the import closure of the root once, **without** environment
   extensions, so no initializer of the submission runs.
2. Classifies every module by the search path entry it is loaded from.
3. Checks every untrusted module in a separate process. The process imports
   the module's imports, reads all parts of the module (including the private
   part of a module-system file) and replays its declarations with
   `Lean.Environment.replay` from Lean core. Inductive types are added again,
   and their constructors and recursors must equal the ones the kernel
   generates. The names under which a module lists its constants must equal
   the constants' own names, because importers look constants up by the listed
   name.
4. Writes one record per module (`dpc.replay/1`): origin, search path entry,
   number of constants, result.

By induction over the module graph, every untrusted declaration has passed the
kernel: each replayed module is checked against its imports, and each import
is either trusted or replayed itself. Unsafe and partial constants are skipped,
as in Lean core's replay. Safe declarations cannot use them.

**One process per module.** Lean maps `.olean` files into memory. Separate
processes share these pages through the page cache, as the `lean` processes
of a `lake build` do. Several environments of a Mathlib-sized closure in one
process would each hold their own copy. `--jobs` (default: the CPU limit of the
sandbox) bounds the parallelism.

**Why not the toolchain's `leanchecker`.**
- It selects modules by name prefix instead of by load location, so the
  shadowing gap would remain.
- It replays all modules as tasks of one process.
- Its output is not structured for the audit log.

**Pipeline.** The replay runs after the build and after the hardened set has
been verified, before the analysis. It logs:
- `replay.completed` (tool run),
- `kernel.replayed` (counts and every failure, plus the SHA-256 of the report),
- one blocking `finding.kernel` per rejected module, and per analysed module
  the replay did not see.

## Consequences

- A submission whose build smuggled in an unchecked proof is blocked, even
  though build, axiom check and analysis all succeed
  (`tests/test_replay.py`, fixture `lean/fixtures/replay`).
- The submission's own modules and its non-official dependencies are checked
  completely. In the quasi-Riemann case that covers 30 dependent formalization
  projects in addition to the repository itself.
- The replay costs roughly the kernel share of the build plus one import per
  module. Quasi-Riemann: 2 943 replayed modules (53 394 declarations) in
  19 min 35 s with 7 processes and 1.7 GB RAM, against about 1 h 40 min for the
  build. Nothing was rejected.
- Projects that put their own modules under a root name of an official package
  (e.g. `Mathlib.Foo` in a non-official package) can no longer be analysed.
  They were already rejected before, by the provenance check.

## What the replay does not cover

- **The trusted base itself.** The official packages come from Mathlib's
  cache and are trusted as far as Mathlib's CI is. A full replay of the
  hardened set (`--fresh` in Lean's terms) is possible, but takes hours. It is
  not done routinely.
- **The kernel.** Lean's kernel is trusted. A second, independent kernel
  (e.g. lean4lean or nanoda) would also guard against kernel bugs.
- **Meaning.** The replay shows that the proofs check, not that the statements
  say what the paper says. That is the class-A review.
- **Rendering.** The ticket views are rendered with the submission's
  environment extensions loaded, so a submission could change how its
  statement is *displayed*. Resolved by [ADR 0011](0011-plain-rendering.md):
  every component is also rendered without the submission's display rules,
  and differences are shown.
