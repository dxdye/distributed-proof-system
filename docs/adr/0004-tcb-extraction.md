# ADR 0004 — Extracting the trusted computing base

Status: accepted (2026-11-08) · implemented in `lean/analyzer`, `dpc/analysis`

## Context

Concept §2 defines `TCB(T)`, `TCB_new(T) = TCB(T) \ H` and the proof internals
`B(T)`; §2.4 sketches an untested Lean metaprogram. Implementing it against
Lean 4.33 surfaced several details.

## Decision

**Edges.** Types always count. Values count for definitions only: theorem
bodies drop out by proof irrelevance, and `opaque` bodies are never unfolded by
the kernel, so they cannot affect meaning. Inductive types contribute their
constructors. Instances are captured automatically because they appear as
constants in types.

**Ticket units.** Compiler-generated declarations are folded into the
declaration a human reviews: constructors and recursors into their inductive,
structure projections into the structure, matchers (`foo.match_1`), auxiliary
proofs (`_proof_n`), `brecOn`/`below`/`casesOn`, `noConfusion` and equation
lemmas (`eq_n`, `eq_def`, `induct`) into their parent.

**Hardened set H.** Determined by the root namespace of the defining module
(`Init`, `Std`, `Lean`, `Mathlib`, `Batteries`, … configurable). `Dep(T)` is not
expanded beyond H. This is exact: hardened libraries cannot import the analysed
repository, so nothing reachable from H lies outside H.

**Imports.** Modules are imported at the `private` level (Lean's module system
would otherwise hide non-exported bodies).

**Two modes.** Loading environment extensions (source ranges, `noncomputable`
and instance flags, matcher info) requires running the `initialize` blocks of
every imported module — foreign code. Therefore:
- `core` mode loads no extensions and runs no foreign code. It is
  authoritative for closures, hashes and axioms.
- `metadata` mode adds presentation data. Python cross-checks it against the
  core run (`dpc/analysis/merge.py`) and treats any disagreement as hostile.
- Matchers are additionally recognised by name so that core mode folds them too.

**Axioms** are collected by walking the full dependency closure ourselves.
`Lean.collectAxioms` is not used because it trusts axiom lists precomputed
inside imported `.olean` files.

**Toolchain.** `.olean` files are bound to the exact Lean version, so the
analyzer is rebuilt per toolchain (cached by toolchain and analyzer source
hash). It depends on Lean core only, which keeps that cheap.

## Findings

- Since Lean 4.3x, `native_decide` no longer uses `Lean.ofReduceBool`; it emits
  an auxiliary axiom `<decl>._native.native_decide.ax_…`. SR-02 still holds
  because every axiom outside Ax0 is flagged; classification recognises both.
- The output is byte-identical on Windows and in the Linux sandbox
  (`test_sandboxed_analysis_equals_recorded_host_analysis`).

## Open points

- **Content hashes are `Expr.hash` (64 bit, not cryptographic).** Fine for
  detecting accidental changes, but a hostile update could be crafted to
  collide and slip past the graph diff (SR-16). Replace with SHA-256 over a
  canonical serialisation of the expression.
- Definitions whose type is a proposition behave like theorems but are
  currently treated as definitions (conservative: more review, not less).
- Very large definitions (concept §19, first open question) are one unit; how
  to split them is a ticket-design question for M4.
