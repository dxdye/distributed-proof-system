# Proposed changes to the concept paper and the SE document

Findings from implementing M0–M3, the Navier–Stokes case study and the
simulation (as of 2026-11-08). Each proposal names the place in the source
document, the proposed change, and the evidence in this repository. "Concept"
refers to the concept paper (draft 2026-10-13), "SE" to the systems engineering
document (draft 2026-10-13). Short quotes keep the original German.

Status legend: **fix** — the document is wrong or outdated; **refine** — more
precise wording; **new** — addition; **decide** — needs a decision by the
document owner.

## Concept paper

### C-01 · §2.2 Axioms — `native_decide` · fix
*Current:* "insbesondere `Lean.ofReduceBool` durch `native_decide`".
*Proposed:* Since Lean 4.3x, `native_decide` no longer uses `Lean.ofReduceBool`
but emits an auxiliary axiom `<decl>._native.native_decide.ax_…`. The rule
"everything beyond Ax₀ is flagged" is unaffected; adjust the example and name
both forms.
*Evidence:* `tests/data/basic/axioms/native_root.jsonl`, `dpc/analysis/axioms.py`.

### C-02 · §2.2 Hardened set H — provenance · refine
*Current:* H is "die Menge der Deklarationen einer festgelegten Mathlib-Version".
*Proposed:* Define H by **provenance**, not by namespace: declarations from the
toolchain or from an official package (Mathlib, Batteries, Aesop, …) at the
pinned revision, fetched from its official repository. A fork named `mathlib`,
or a module `Mathlib/Evil.lean` in another package, must not count as hardened —
otherwise it silently removes definitions from TCB_new.
*Evidence:* ADR 0005, `dpc/analysis/hardening.py`, `tests/test_workspace.py`.

### C-03 · §2.4 TCB sketch — completion · refine
*Proposed additions to the sketch:*
1. Ticket units: fold compiler-generated declarations (matchers `match_n`,
   `_proof_n`, `brecOn`/`below`/`casesOn`, `noConfusion`, equation lemmas) and
   constructors, recursors and structure projections into the declaration they
   belong to.
2. `opaque` bodies do not belong to the TCB (the kernel never unfolds them).
3. Import at the `private` level; Lean's module system otherwise hides bodies.
4. Collect axioms by an own closure walk; `Lean.collectAxioms` trusts axiom lists
   stored in `.olean` files.
5. Hardened declarations need not be expanded when computing `Dep(T) \ H` (H
   cannot import the repository) — exact and much cheaper.
*Evidence:* ADR 0004, `lean/analyzer`, `lean/fixtures/basic` with hand-checked TCB.

### C-04 · §2.4 "Erster empirischer Schritt" — result · new
*Proposed:* Record the measurement for Navier–Stokes: |TCB(T)| = 5 571,
**|TCB_new(T)| = 15 declarations (8 ticket units, 116 lines)**, B_new = 23 820
units, axioms = Ax₀. QRH 7/8 follows.
*Evidence:* `docs/case-studies/navier-stokes.md`.

### C-05 · §5.1 Equivalence filter · fix
*Current:* "wenn er typkorrekt ist und sich M ↔ D nicht automatisch beweisen lässt".
*Proposed:* For a proven theorem D, `M ↔ D` is provable exactly when M is true,
so the filter would discard every true mutant — including the subtle, faithful-
looking but different claims that make the best honeypots. Replace by: "… and
the changed part cannot automatically be proven equivalent **in its local
context**" (relations `a ↔ a'`, terms `t = t'`, dropped hypotheses derivable from
the others). Add: (a) mutants must be **visible** in the ticket rendering
(binder types shown; a change hidden in `ℝ³ → ℝ⁴` cannot fairly be expected to
be found); (b) structures are mutated through their constructor fields.
*Evidence:* ADR 0007, `tests/test_mutation.py`.

### C-06 · §5.1 Limits of automatic filtering · new
*Proposed:* State that the filter is a semi-decision. Example from
Navier–Stokes: `C / (1 + ‖x‖)^K` → `C / (2 + ‖x‖)^K` under `∃ C` is equivalent
(the constant absorbs it) but not provably so by local tactics. Therefore the
honeypot pool of a campaign is checked by a maintainer before use (feasible:
47 candidates for Navier–Stokes).
*Evidence:* `docs/case-studies/navier-stokes.md`, section "Honeypot candidates".

### C-07 · §5.1, §15, FMEA R1 — Honeypot lookup · decide
*Current (§15):* "Mutanten aus vielen Quellen; der Abgleich kostet ähnlich viel
Aufwand wie ein echtes Review".
*Proposed:* For public repositories the comparison takes about a minute and
also reveals which tickets are real. The simulation shows lookup attackers
earning **more** trust than honest reviewers and raising the miss rate to up to
15 % (`k_min = 2`). Options: review before publication (embargo), private pools
of non-public formalizations, informal-side honeypots (genuine Lean, altered
informal statement). Decision on extending the specification pending.
*Evidence:* ADR 0006, `docs/simulation/README.md`.

### C-08 · §5.1 Honeypots and automatic lints · new
*Proposed:* A mutant that an automatic lint (junk values, vacuity attempt)
already detects measures the linter, not the reviewer: exclude it from the
honeypot pool or use it to test the linter.
*Evidence:* ADR 0007 (consequences); implementation planned in M2.

### C-09 · §6.2 Evidence table · refine
*Proposed:* The table layout is ambiguous. State the general rule used in the
implementation: a verdict on an item that is erroneous with probability
`p_error`, weight `w`, updates `s` with weight `w·p_error` (success = "incorrect")
and `c` with weight `w·(1−p_error)` (success = "correct"). Honeypots and
refutations: `p_error = 1`, `w = 1`; PVV re-check: the PVV's verdict as truth,
`w ≈ 0.5`; consensus: Dawid–Skene posterior, `w ≈ 0.2`.
*Evidence:* `dpc/domain/trust.py`.

### C-10 · §6.4, §9, §18 — Parameters · refine
*Proposed:* Initial values from the simulation: `k_min = 3` (robustness against
gaming: miss rate under attack 0–6 % instead of up to 15 %), θ_PV ≈ 0.3–0.45 (at
0.6 fewer than 10 % of honest reviewers qualify), honeypot share h = 0.05–0.1
(a higher h costs volunteer time and gives lookup attackers more free credit).
*Evidence:* `docs/simulation/parameter-study.md`.

### C-11 · §16 Pipeline, step 1 — trusted and untrusted steps · refine
*Proposed:* Spell out the trust boundary:
1. fetch the repository and all dependencies with plain git at pinned commits
   (never run Lake here — it would execute the submission's lakefile with
   network access);
2. Mathlib cache with Mathlib as the Lake root;
3. integrity snapshot of the hardened packages;
4. build and analysis in the sandbox, without network;
5. verify the snapshot; any change to a hardened source or `.olean` is blocking.
A workspace that has run foreign code never runs a trusted step again.
*Evidence:* ADR 0005; both rules came from failures found in the case studies.

### C-12 · §16 Build is mandatory · new
*Proposed:* State why the system builds itself instead of accepting prebuilt
`.olean` files from the submitter: the analysis needs the elaborated
environment; the build is the independent PRL 0 → 1 check; and `.olean` files
are not re-checked on import, so only an own build binds the analysis to the
sources of the commit. An additional kernel replay (lean4checker, Comparator) of
the submission's own `.olean` files is planned.

### C-13 · §2.2 / §14 — Reviewed reference statements · new idea
*Proposed:* Navier–Stokes states its main theorem through reference definitions
taken from Formal Conjectures and checks it with Comparator; this is why TCB_new
is tiny. Reviewed reference statements could be treated like H and shared
across projects, so that class A of later submissions shrinks further.
*Evidence:* `docs/case-studies/navier-stokes.md`, consequences.

### C-14 · §8.1 Static difficulty · refine
*Proposed:* Name the static features actually available from the analysis:
direct dependencies, depth in the TCB, source lines, instances among the
dependencies, noncomputable members (standardised per campaign, provisional
weights, IRT calibration in the pilot).
*Evidence:* `dpc/tickets/difficulty.py`.

### C-15 · §19 Large definitions · refine
*Proposed:* Large definitions are mostly structures; their meaning lives in the
constructor fields. A ticket unit is the structure with its fields; for large
structures, one ticket per field (or per group of fields) is a natural split.

## SE document

### S-01 · AS-1 and §9 workload · fix
*Current:* AS-1 "|TCB_neu| ≈ 500 für NS"; §9 concludes the bottleneck is
expertise in class A.
*Proposed:* Measured for Navier–Stokes: 15 declarations (8 units). Class A needs
about 36 reviews; the work lies in class B (23 820 units). Revisit §9 per
project: for repositories with reference statements and Comparator, the
bottleneck moves to class B.
*Evidence:* `docs/case-studies/navier-stokes.md`.

### S-02 · SR-01 Reproducible build · refine
*Proposed addition:* "`lake-manifest.json` is required; dependencies are git
repositories pinned to full commit hashes; the submission's lakefile is not
executed outside the sandbox."
*Evidence:* `dpc/ingest`, `tests/test_ingest.py`.

### S-03 · SR-07 Mutants · refine
*Proposed:* "Mutants shall be type-correct, *visible* in the ticket rendering, and
shall not be provably equivalent at the place of the change (concept §5.1
revised, ADR 0007)."

### S-04 · SR-16 Graph diff · refine
*Proposed addition:* "Content hashes shall be cryptographic and invariant under
renaming of bound variables." (A 64-bit structural hash can be collided by a
hostile update.)
*Evidence:* ADR 0004, `tests/test_lean_e2e.py::test_renaming_bound_variables_is_not_a_change`.

### S-05 · SR-20 Isolation · refine
*Proposed addition:* "The analysis of foreign `.olean` files also runs in the
sandbox. Trusted steps (with network) never run in a workspace in which foreign
code has run. Hardened packages are verified against a snapshot taken after the
last trusted step."

### S-06 · New requirement: provenance of H · new
*Proposed:* "SR-61: Hardened packages are accepted only from their official
sources; every declaration treated as hardened must come from the toolchain or
from such a package at the pinned revision."

### S-07 · CN-2 Open Source · fix
*Current:* "Open Source. Berichte und Befunde sind öffentlich."
*Proposed:* "Source code published as source-available (non-commercial use);
reports and findings are public under an open license." (A non-commercial
license is not open source in the usual sense.)

### S-08 · FMEA — new failure modes · new
| Failure mode | Effect | Measure (status) |
|---|---|---|
| Build-time code writes forged `.olean` files of the submission | false result accepted | kernel replay (planned) |
| Hostile update crafted to collide a 64-bit content hash | change escapes the graph diff | SHA-256 Merkle digest (done) |
| Module placed under a hardened namespace / forked Mathlib | definitions vanish from TCB_new | provenance check (done) |
| Untrusted build tampers with a hardened lakefile, next trusted step runs it with network | infrastructure compromise | no trusted step after foreign code (done) |
| Elaboration error recovery closes an equivalence goal with `sorry` | equivalent mutant used as honeypot | strict proof check (done) |
| Mutation hidden in an unrendered type | unfair honeypot | visibility check (done) |
| R1 honeypot lookup | trust inflated | detection D should be rated higher; see C-07 |

### S-09 · §12 TPM "Build + Analyse für 300k Zeilen" · new evidence
Navier–Stokes, ≈ 382 k lines: about 34 minutes end to end with 7 CPUs
(target ≤ 2 h: met).

### S-10 · OD-5 Values of h, ρ, θ, δ_A · decide
Proposal from the simulation, see C-10.

### S-11 · §11.2 Verification — done items · new
Implemented verifications: TCB on hand-checked mini repository incl. property
"changing a proof does not change the TCB" (SR-03); graph diff on commit pairs
(SR-16); red-team build without network and write access (SR-20); simulation
of κ convergence and decision error rate (SR-11/12); Plackett–Luce recovery
(SR-38); equivalence filter on mutants with known equivalence (SR-07); plus
byte-identical analysis on Windows and in the Linux sandbox. The traceability
matrix is generated with `pixi run trace`.
