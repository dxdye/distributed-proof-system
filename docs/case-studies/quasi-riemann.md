# Case study: ζ(s) ≠ 0 for Re s > 7/8 (openai/math)

Measured 2026-11-08/09 with the M1 pipeline (`dpc ingest --executor docker-volume`),
views and honeypot candidates with the M2/M4 tools (`dpc render`, `dpc mutate`).
Second case study after [Navier–Stokes](navier-stokes.md), same questions
(concept §2.4: how large is |TCB_new| really?).

## Submission

| Field | Value |
|---|---|
| Repository | https://github.com/openai/math (Lean project in `lean/`) |
| Commit | `4eaee87548250b2682affda7d05d947c05554bae` |
| Main theorem | `OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re` |
| Module | `OAI.NumberTheory.DirichletL.Nonvanishing` |
| Toolchain | `leanprover/lean4:v4.34.1` |
| Dependencies | 42 packages: Mathlib and its inherited packages (official), 30 further formalization projects |
| Dependency patches | 23 compatibility patches (`patches/<package>-lean4341.patch`, one per third-party package), applied in the trusted fetch step (ADR 0005) |
| Artifact key | `6fbb5d0b578a13b9cc3b3396c0b79b004884d1dff48d44f317bf18362335b96d` |

## Results

| Measure | Value |
|---|---|
| Axioms | `propext`, `Classical.choice`, `Quot.sound` (= Ax₀, no finding) |
| \|TCB(T)\| | 4 962 declarations |
| hardened part (Mathlib, core) | 4 961 declarations |
| **\|TCB_new(T)\|** | **1 declaration = 1 ticket unit = 4 lines: the main statement itself** |
| B_new(T) (proof internals) | 19 442 ticket units |
| Provenance of hardened modules | all verified |
| Integrity of hardened packages | unchanged by the build (54 388 files checked before and after) |
| Kernel replay (ADR 0009, 2026-11-13) | 8 596 modules in the closure: 1 552 toolchain and 4 101 official-package modules trusted by location; **2 943 modules replayed** (the repository and its 30 non-official dependencies), **53 394 declarations, none rejected**; 10 unsafe or partial constants skipped |

The class-A ticket in full, as a reviewer sees it (`dpc render`):

```
∀ {s : ℂ}, 7 / 8 < s.re → riemannZeta s ≠ 0
```

Glossary: `Complex`, `Complex.re`, `HDiv.hDiv`, `LT.lt`, `Nat`, `Ne`, `OfNat.ofNat`,
`Real`, `riemannZeta`. Everything the statement uses is Mathlib. What a
reviewer has to check is therefore short but not empty:
- that `7 / 8` is real division, not natural-number division (which would give
  `0`). The junk-value question of the checklist; the hover types show `s.re : ℝ`.
- that the bound is strict.
- that `riemannZeta` is Mathlib's analytic continuation, not a local
  redefinition (provenance check: yes).

The domain heuristic classifies the unit as *algebra*; number theory is meant.
This is a maintainer correction (SR-04), as for `divergence` in the
Navier–Stokes study.

## Timings (7 CPUs, 24 GB, Docker Desktop on Windows)

| Step | Duration |
|---|---|
| Fetch (git, repository and 42 packages, 23 patches) | 4 min 7 s |
| Mathlib cache (trusted, one transient retry) | 2 min 8 s |
| Snapshot of hardened packages (54 388 files) | 9 s |
| Build of the import closure (7 061 jobs) | ≈ 1 h 40 min (15 min, interrupted on purpose, then 84 min incremental) |
| Analysis, core run | 136 s |
| Analysis, metadata run | 167 s |
| Kernel replay (added 2026-11-13; 7 processes, 1.7 GB RAM) | 19 min 35 s |
| **Total** | **≈ 1 h 50 min** |

Before the run succeeded, it surfaced two problems that are fixed:
- The repository's own compatibility patches (ADR 0005, "dependency patches")
  were missing: without them the pinned revisions of the third-party packages
  do not build on this toolchain.
- Lake stores escaped package names (`«tate-curves-theta»`) whose directories
  are plain.

The interrupted build was resumed on the same volume. The stored snapshot was
re-verified first (`hardened.reverified`), as the invariant of ADR 0005
requires.

## Honeypot candidates (M2)

| Candidates | Type-incorrect | Provably equivalent | Invisible | Usable |
|---|---|---|---|---|
| 13 | 6 | 0 | 0 | **7** (constant 5, relation 1, drop hypothesis 1) |

| Mutant | Meaning |
|---|---|
| `6 / 8 < s.re` | a much stronger claim; open as far as we know |
| `8 / 8 < s.re`, `7 / 7 < s.re` | weaker, *true* claims (the classical zero-free half-plane Re s > 1) |
| `7 / 9 < s.re` | stronger, different from the paper |
| `7 / 8 ≤ s.re` | includes the line Re s = 7/8: subtle, a good honeypot |
| `riemannZeta s ≠ 1` | a different conclusion |
| hypothesis dropped | `∀ s, ζ(s) ≠ 0`: false (trivial zeros) |

Two of the mutants are true theorems. They are still planted errors in the
sense of concept §5.1: the formal statement no longer says what the paper
says. A reviewer who checks only plausibility instead of fidelity will miss
them. This is exactly what honeypots are meant to measure.

## Consequences for the design

1. **AS-1 fails again, more drastically.** One class-A ticket for a result
   whose proof spans ≈ 19 000 units. Review effort for the *statement* is
   about 4 reviews. For the second time, the trusted base is small because the
   statement is expressed through reference definitions — here Mathlib itself.
2. **No own honeypots for one-ticket submissions.** At `h = 0.1`, one real
   ticket gets `round(1 · 0.1 / 0.9) = 0` honeypots. A submission like this one
   can only be calibrated with honeypots from other sources, which is the
   cross-submission case of ADR 0006. Showing a honeypot of declaration X
   inside a submission that does not contain X would stand out, though.
   Honeypot streams should therefore mix across papers, not within one paper.
   The choice sets (SR-38) already present tickets from different papers.
3. **The remaining risk sits in the proof artefacts, not in the statement.**
   The class-A review is quick. Whether the result holds depends on the
   kernel having checked the 19 442 proof units. The build ran in the sandbox
   from source, but build-time code of the repository itself could have
   written forged `.olean` files for its own modules (ADR 0005, open point).
   For submissions of this shape, **replaying the environment through the
   kernel is the most valuable next check**, more valuable than any human
   review of class B. The evidence checker of SR-10 already replays the
   evidence module this way (`dpc-evidence`). Extending it to the submission's
   own modules is the same mechanism at a larger scale.
   *Implemented since:* [ADR 0009](../adr/0009-kernel-replay.md) replays every
   module not loaded from the toolchain or an official package, here the
   repository and its 30 non-official dependencies. On this volume it replayed
   2 943 modules with 53 394 declarations in under 20 minutes and rejected
   none: the proof artefacts of this submission passed the kernel.
4. **Class B as defined by the concept matters less here.** Sampling proof
   internals finds errors that do not change the meaning of the statement.
   For a reuse-oriented library (Mathlib-style) class B is relevant; for a
   single-result repository it mostly matters as a guard against unchecked
   proof artefacts, which point 3 covers better.
