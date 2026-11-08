# Case study: Navier–Stokes blow-up (openai/NavierStokesAndEuler)

Measured 2026-11-08 with the M1 pipeline (`dpc ingest --executor docker-volume`).
First empirical step named in concept §2.4: measure |TCB_new| for the case studies.

## Submission

| Field | Value |
|---|---|
| Repository | https://github.com/openai/NavierStokesAndEuler |
| Commit | `f9e8bc5b38b6e212696e8a30e3e91517af887bbd` |
| Main theorem | `NavierStokes.Comparator.navier_stokes_breakdown_R3` (alternative (C), ℝ³) |
| Module | `NavierStokes.ComparatorSolution` |
| Toolchain | `leanprover/lean4:v4.34.0-rc2` |
| Dependencies | Mathlib (official, `v4.34.0-rc2`), Comparator, and their inherited packages |
| Artifact key | `a1dba58c4d38228f47211f3ab9d90e2edef570ac9bb0e878dd5d00b696b70005` |

## Results

| Measure | Value |
|---|---|
| Axioms | `propext`, `Classical.choice`, `Quot.sound` (= Ax₀, no finding) |
| \|TCB(T)\| | 5 571 declarations |
| hardened part (Mathlib, core) | 5 556 declarations |
| **\|TCB_new(T)\|** | **15 declarations = 8 ticket units = 116 lines** |
| B_new(T) (proof internals) | 23 820 ticket units |
| Provenance of hardened modules | all verified (no module outside toolchain/official packages) |
| Integrity of hardened packages | unchanged by the build (53 371 files checked) |

Class-A units (deg⁻ = number of other units using it; domain by heuristic):

| Unit | deg⁻ | Domain |
|---|---|---|
| `NavierStokes.Comparator.ForceConditionDecay` | 5 | analysis |
| `NavierStokes.Comparator.NavierStokesExistenceAndSmoothnessRn` | 5 | analysis |
| `NavierStokes.Comparator.divergence` | 5 | algebra ⚠ |
| `NavierStokes.Comparator.InitialVelocityConditionDecay` | 4 | analysis |
| `NavierStokes.Comparator.NavierStokesExistenceAndSmoothness` | 3 | analysis |
| `NavierStokes.Comparator.ForceCondition` | 2 | analysis |
| `NavierStokes.Comparator.InitialVelocityCondition` | 2 | analysis |
| `NavierStokes.Comparator.navier_stokes_breakdown_R3` | 0 | analysis |

These are precisely the items of the review checklist in concept §17.1
(initial data and decay, force, notion of solution, energy bound, the
"breakdown" statement itself).

⚠ `divergence` is classified as algebra because its definition uses the trace
of the Jacobian (linear algebra); the intended domain is analysis. This is the
case for maintainer corrections (SR-04).

## Timings (7 CPUs, 24 GB, Docker Desktop on Windows)

| Step | Duration |
|---|---|
| Fetch (git, repository and 11 packages) | 27 s |
| Mathlib cache (trusted, Mathlib as Lake root) | 128 s |
| Snapshot of hardened packages | 9 s |
| Build of the import closure (609 modules, ≈ 382 k lines) | 25 min 43 s |
| Analysis, core run | 147 s |
| Analysis, metadata run | 176 s |
| **Total** | **≈ 34 min** |

TPM "build + analysis for 300 k lines" (SE §12): target ≤ 2 h — met.

## Consequences for the design

1. **Assumption AS-1 does not hold for this case.** The workload estimate in
   SE §9 assumes |TCB_new| ≈ 500 for Navier–Stokes. Measured: 15 declarations.
   The repository states its main theorem through reference definitions taken
   from Formal Conjectures (Google DeepMind) and checks it with Comparator, so
   the trusted base that needs review is small.
2. **The bottleneck moves from class A to class B.** Class A needs about
   8 × 4.5 ≈ 36 reviews (≈ 12 expert hours); class B has 23 820 units to sample
   from. The SE §9 conclusion ("the bottleneck is expertise in class A") should
   be revisited per project.
3. **Review effort for class A concentrates on the reference definitions.** If
   the same reference definitions (Formal Conjectures) are used by several
   projects, their review can be shared — an argument for treating reviewed
   reference statements like the hardened set H.
4. The first run surfaced two design issues that are fixed (ADR 0005): Lake
   rewrites its own `.olean.hash` files (excluded from the integrity check), and
   reusing a workspace after an untrusted build must never re-snapshot or run a
   trusted step again.
