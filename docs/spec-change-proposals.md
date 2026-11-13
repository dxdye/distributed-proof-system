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

### C-16 · §16 Dependency patches · new
*Proposed:* Formalizations may patch their dependencies for toolchain
compatibility (`openai/math`: 24 patches, partly applied by the lakefile at
configuration time). State that declared patches are applied by the system,
hashed and published in the report, and that patched dependency code belongs
to the review — the build is "repository + dependencies at pinned revisions +
declared patches", not upstream code. Patches to hardened libraries are not
allowed.
*Evidence:* ADR 0005, `dpc/lean/workspace.py` (`map_patches`), QRH case study.

### C-17 · §12.6 AI use during review — goal and enforcement · refine
*Current:* "KI-Hilfe ist erlaubt, muss aber angegeben werden." Models of the
provider of the reviewed proof are excluded; similar justifications are
searched for.
*Proposed:*
1. State the goal: **verdict and justification must be the reviewer's own.**
   AI may be used as a tool (looking up definitions, explaining notation,
   translating), but a verdict passed on from a model is not what the system
   credits.
2. State how the rule is enforced. A ban cannot be enforced, because nobody can
   see whether a reviewer has a model open in another window. Delegation is
   made unprofitable instead: an account that hands tickets to a model inherits
   the model's misses on honeypots and loses trust, whether or not it declared
   the use. The honeypots are the enforcement mechanism.
3. Name the condition this rests on: **honeypots must be as hard for models as
   real errors.** A mutant that current models detect reliably measures the
   model, not the reviewer, just as a mutant that a lint detects measures the
   lint (C-08). Such mutants are removed from the pool by a model-detection
   filter, re-run against current models for every campaign. Otherwise
   delegating accounts earn *more* trust than honest reviewers, which is the
   lookup attack of C-07 in another form.
*Evidence:* `docs/simulation/README.md`: lookup attackers out-earn honest
reviewers; honeypots 2.5 IRT units easier than real errors raise the miss rate
from 4.9 % to 8.0 %. Open: measure how many honeypots of the case studies
current models miss, compared with real errors.

### C-18 · §16 Pipeline, §2.2 — Kernel replay and trust by location · new
*Proposed:* Lean does not re-check `.olean` files on import, and the build runs
the submission's code. Add a pipeline step after the build: every module that
is not loaded from the toolchain or an official package is replayed through
the kernel. Modules are trusted by the place they are loaded from, not by
their name. The search path lists the toolchain first, then the official
packages, then the project; otherwise a build could shadow `Mathlib` or `Init`
with forged copies in its own build directory. A rejected module is a blocking
finding.
*Evidence:* ADR 0009, `tests/test_replay.py`:
- A theorem added under `debug.skipKernelTC` passes the build and the axiom
  check, but not the replay.
- A planted `Init` in the build directory is never loaded.

Quasi-Riemann: 2 943 modules with 53 394 declarations replayed in 19.6 min, none
rejected.

### C-19 · §8.8 Tools in the ticket — two renderings · new
*Proposed:* A submission's own display rules (notation, coercions, unexpanders,
delaborators) can change what reviewers see, e.g. print `a ≤ b` as `a < b`.
Every component is therefore also rendered without them, by a process that
runs no code of the submission. Where the two renderings differ, both are
shown, and the plain one is binding.
*Evidence:* ADR 0011, fixture `lean/fixtures/display`. Case studies: no
differences in 16 components and 54 mutants.

### C-20 · §8.8, OS-3 — Paper passage and typeset formula · refine
*Proposed:* A ticket shows the informal statement from the paper next to the
Lean statement. A maintainer maps it, and reviewers can contest it (SR-24). The
ticket also shows the Lean term itself typeset as LaTeX: mechanically, one
rendering per construct, nothing guessed. Division and subtraction on ℕ and ℤ
are marked, and casts show their target type. State that such typesetting of
the *same term* is not a back-translation in the sense of SR-36. Free
translations stay behind round 1.
*Evidence:* ADR 0012. Without the paper side, true-but-different honeypots
(quasi-Riemann `8/8 < s.re`, `7/7 < s.re`) cannot be detected, so they measured
nothing.

### C-21 · §8.1, §6.3 — Difficulty tiers and who may take them · new
*Proposed:* Show coarse, absolute tiers (easy, medium, hard, excellence),
computed from what the reviewer sees:
- the amount of text;
- the constants used, with library and submission constants weighing more;
- the quantifier alternations.

The b_i of §8.1 is standardised per campaign and therefore unfit as a label:
the average ticket of every paper would read "medium".
- Hard tickets need the PV role in the domain, excellence tickets the PVV role.
- A self-declared group opens nothing.
- After 14 days every ticket is open to everyone (SR-05).

Thresholds are to be calibrated in the pilot (IRT).
*Evidence:* `dpc/coord/tiers.py`. Navier–Stokes: 5 hard, 3 excellence;
quasi-Riemann: medium; fixtures: easy.

### C-22 · §10.2 Choice sets — preferences · new
*Proposed:* Reviewers may state domains and tiers they prefer.
- Preferences fill at most half of a choice set. The rest is drawn at random,
  and the set is shuffled.
- Preferences are ignored when the matching tickets come from fewer than two
  submissions. Otherwise a domain with one paper would deliver that paper's
  tickets on request, which is the steering SR-38 prevents.

*Evidence:* `Coordinator.choice_set`,
`test_preferences_raise_the_chance_but_cannot_steer`.

### C-23 · §5, §8.5 — An "incorrect" verdict names the failing question · refine
*Proposed:* A claim names which of the five checklist questions fails and gives
a justification of at least 30 characters. This makes claims decidable for
PVVs and lets them be evaluated per question.
*Evidence:* In the first walkthrough a claim "idk" was accepted and cost a
maintainer's time.

### C-24 · §6.5, C12 — Sign-in · new
*Proposed:*
- Sign-in through any OpenID Connect provider: Keycloak for the pilot, a
  university's single sign-on by configuration, SAML through brokering.
- Only the coarse maintainer role may come from the provider, and every grant
  and revocation is logged. PV and PVV never come from outside.
- Accounts stay pseudonymous: a separate vault links the provider's subject to
  the reviewer id, and the audit log never sees it.

*Evidence:* ADR 0010.

### C-25 · §8.9 Learning loop — discussion after the decision · new
*Proposed:* A community platform needs a place to talk about the work, or
community-minded reviewers feel alone and learn little. Add a discussion per
declaration to the learning loop, under rules that keep the measurement
intact:
- **When.** A declaration's thread opens only when all of its tickets are
  decided and no planted error of the submission is still unrevealed. Before
  that, a discussion would bind later verdicts into one chain (§9.4, R13).
  Opening per declaration would also show, by its timing, which declaration
  still has an open planted copy.
- **What.** A reviewer can share their own verdict and justification, and
  anyone signed in can comment. Planted errors are not discussed publicly:
  whoever missed one gets the explanation privately (§8.9, "sonst lernen PV die
  Muster der Mutationen").
- **Votes.** Up- and downvotes sort the posts. They never enter trust, roles or
  decisions: trust must not grow from mutual agreement. There is no karma per
  person.
- **Who.** Posts are anonymous by default ("Reviewer A, B, …" per thread). The
  pseudonym is optional, per thread, because it links the person to all their
  reviews in the published audit log (SR-23). Shown on every post:
  - whether the author is a maintainer, so that statements are weighed
    accordingly;
  - since when the author has taken part, by month.
- **Back into the process.** A post that shows a decided declaration to be
  wrong can be raised as a reopen request. A maintainer either turns it into
  an escalation, which is decided like any other (§6.4), or dismisses it.
  Discussion itself never changes a decision.
- **Hygiene.** Reporting and moderation by maintainers. Posts are licensed like
  reviews (SR-49), and AI use is declared (SR-48).

The threads grow into the error catalogue of §8.9 and are a natural place to
propose definition tests (§5.2).
*Evidence:* Walkthrough with the project owner (2026-11-14).

### C-26 · §11.1 Anytime reports, §10.1 PRL, §10.3 The map — a public progress page · refine
*Proposed:* The concept already asks for a report at any time (class-A coverage,
the class-B bound, the PRL), interim reports at a fixed cadence (SR-42) and a
map of attention against PRL (§10.3). Make it a public, live page, readable
without signing in, so that everyone sees the big picture and reviewers see
what they are part of. Per submission it shows:
- the problem: title, the paper, the informal main statement;
- the PRL with its meaning;
- class-A coverage in % and declarations by state (accepted, error found, in
  review);
- confirmed findings, and the estimated probability that an accepted
  declaration is wrong;
- a forecast (P50/P85) once throughput has been measured;
- interest per paper (ψ, §10.2), progress over time;
- notes by maintainers, which signed-in users can vote up or down.

Rules that keep the page from leaking or anchoring:
- **Counts are by declaration, never by ticket.** Ticket counts would expose
  the number of planted errors.
- **A declaration counts as decided only when all of its tickets are.**
  Otherwise someone holding a planted copy would learn from the page that the
  real ticket is already decided.
- **The Lean statement of the main theorem is shown only once its declaration
  is decided and the planted errors of the submission are revealed.** Before
  that, the paper's statement is shown, which is the same for the real ticket
  and its copies.
- **No live verdict tallies** (share of "faithful" or "problem found"). They
  would anchor reviewers (§10.5 "Beliebtheit erst nach der Wahl", §9.4) and
  move with planted errors. What is shown is decided and confirmed results.
- **No up- or downvotes on submissions.** Votes on a lab's work invite
  brigading and pressure (FMEA R21); interest is measured from choices with
  completed work, weighted by trust (§10.5). Votes apply to maintainer notes
  only, for sorting.

*Evidence:* Walkthrough with the project owner (2026-11-14).

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

### S-02a · SR-01 Dependency patches · refine
*Proposed addition:* "Declared dependency patches are applied by the system,
hashed and listed in the report; patches to hardened libraries are rejected."
Observed: `openai/math` at `4eaee87` does not build from the pinned manifest
alone (`rellich-kondrachov` fails against the pinned Mathlib without its patch).

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

### S-12 · SR-48 AI use · refine
*Proposed:* "AI use during review must be declared. Verdict and justification
must be the reviewer's own. A submission records the provider of the model that
generated the proof; reviews declaring a model of that provider are excluded.
Honeypot pools are filtered against detection by current models (concept §12.6,
C-17)." Add the model-detection filter to the measures of FMEA R20.
*Status:* The declaration exists (`AIAssistance` in `dpc/tickets/model.py`, a
provider is required). The provider exclusion is not enforced yet, because a
submission does not record the proof's provider. Neither the similarity analysis
nor the model-detection filter exists yet.

### S-13 · New requirement: kernel replay · new
*Proposed:* "Every declaration that is not loaded from the toolchain or an
official package shall be re-checked by the kernel before the analysis. Modules
are trusted by the location they are loaded from, not by their name. A
rejected module is a blocking finding." See C-18.

### S-14 · SR-21 Infoview · refine
*Proposed:* "… with an infoview: types, origin and docstring of every constant,
go-to-definition. Every statement is also rendered without the submission's
own display rules, and differences are shown." See C-19. Go-to-definition is
not implemented yet.

### S-15 · SR-24 Paper mapping · fix (milestone)
*Proposed:* Move SR-24 from M6 to M4. The pilot cannot review fidelity without
the paper side. For the pilot, a maintainer maps; later, mapping tickets before
class A. See C-20.

### S-16 · SR-36 Aids after round 1 · refine
*Proposed:* "Aids that interpret the statement (e.g. back-translation) shall
only be shown after round 1. A mechanical typesetting of the same term is not
such an aid." See C-20.

### S-17 · SR-32, SR-38 Preferences · refine
*Proposed:* Add to SR-38: "Preferences of the reviewer fill at most half of a
choice set and apply only where the matching tickets come from at least two
submissions." See C-22.

### S-18 · SR-09 Justification · refine
*Proposed:* "An 'incorrect' verdict names the failing checklist question and
gives a justification of at least a minimum length." See C-23.

### S-19 · SR-30 Expected duration · refine
*Proposed:* "… only the expected duration, once it has been measured; before
that, none." Showing the default lease length as the expected duration (45
minutes for a four-line statement) misled reviewers.

### S-20 · C4 Technology, OD-1, OD-2 · refine / decide
- *C4:* SQLite with a projection rebuilt from the audit log for the pilot;
  PostgreSQL once several instances are needed (ADR 0002, ADR 0008).
- *OD-1, OD-2:* Who operates the system and who appoints maintainers were due
  before M4 and are still open. Technically, maintainers are a role in the
  identity provider (C-24). Operator under discussion: a university (pilot with
  students).

### S-21 · New requirement: discussion after the decision · new
*Proposed:* "The discussion of a declaration shall open only when all of its
tickets are decided and no planted error of the submission is unrevealed.
Planted errors shall not be discussed publicly. Posts are anonymous unless the
author chooses to show their pseudonym; whether the author is a maintainer,
and since when they take part, is shown." See C-25.

### S-22 · New requirement: votes carry no weight · new
*Proposed:* "Votes on posts shall influence neither trust, roles nor
decisions. A post can lead to a change of a decision only through a reopen
request decided by a maintainer." See C-25.

### S-23 · SR-42 Interim reports — a public progress page · refine
*Proposed:* Add to SR-42: "The anytime report of every submission is public
and live: PRL, class-A coverage, decided declarations, confirmed findings,
estimated residual error and forecast. It counts declarations, not tickets,
counts a declaration as decided only when all its tickets are, and shows no
live verdict tallies." See C-26.
