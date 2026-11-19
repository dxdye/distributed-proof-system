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
*Decided for public examples (2026-11-15):* the front page and other public
teaching material show only a declaration that is decided and whose paper has
no unrevealed planted error. An example under review tells every reviewer what
to look for in exactly that ticket, and its risks can resemble its planted
copies (QRH: "Re(s) > 1" next to the candidates `8 / 8 < s.re`, `7 / 7 < s.re`):
a side channel like the lookup above. The front page now shows Navier–Stokes
(the regularity condition of its definition of a smooth solution, 2026-11-15):
it shows the work of many tickets better than QRH, whose meaning lies in a
single line. In the test system that paper is not fully decided, so the
example does not meet the rule yet; it must before any launch.
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
- Domain and difficulty must both match. Difficulty is chosen as an upper
  bound, "up to Hard": every tier up to and including it. That matches "not
  harder than", and more tickets match. Locked tiers stay locked.
- The reviewer learns when the preferences could not be used for a set, never
  why: "only one paper has such tickets" would tell which paper has them.
  Which tickets of a set match stays invisible too; the order is random.
- Set size stays at 4 in the pilot: with few open papers, "one ticket per paper
  first" cannot be met for 6, and exclusions often leave fewer tickets. Before
  going to 6 (at least six open papers), measure how often planted copies are
  chosen from a set compared with real tickets of the same sets, from
  `choice_set.drawn`, `lease.granted` and the revealed planted errors. If they
  are chosen clearly less often, reviewers avoid them and the set is too large.
  The measure is a health check of the choice mechanism at any size. For
  targeting: the limit of 24 sets a day weighs more than the set size (a
  given ticket among 200: about 38 % a day with 4, 52 % with 6).
- Limits on rerolling, preferences at sign-up and a bound τ_max: C-32.

*Evidence:* `Coordinator.choice_set`,
`test_preferences_raise_the_chance_but_cannot_steer`; walkthrough with the
project owner (2026-11-15): "analysis, up to Hard" brought no matching ticket
and no explanation.

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
- **Votes on a thread** (added after the walkthrough, 2026-11-14) say whether
  the discussion is worth reading and sort the list of discussions. They are
  not a vote on the decision: an unweighted public poll on a decision would put
  pressure on maintainers and anchor the reviewers of a reopened declaration.
  Votes on threads are no side channel for planted errors, because threads
  open only after every planted error of the submission is revealed.
- **Reports** can be withdrawn while maintainers have not acted on them; a post
  that is already hidden stays hidden.
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

### C-27 · §3 question 2, §14 Mathlib hardening — Mathlib in the statement: its use and its definitions · new
*Current:* Class A covers TCB_new(t) = Dep(t) \ H; Mathlib declarations are
hardened by assumption. Question 2 of §3 asks about junk values where the
statement uses them. §14 applies the same system to Mathlib itself (priority 1:
TCB(t) ∩ M), but does not say how this connects to the review of a submission.
*Problem:* The more a statement is phrased in Mathlib's vocabulary, the smaller
class A gets, and the meaning moves into Mathlib. QRH: TCB_new(t) is a single
declaration, the main theorem. What it says depends on `riemannZeta`,
`Complex.re` and real division, and none of them is reviewed. Two things can
go wrong:
1. *Use.* A Mathlib definition is correct but does not mean here what the paper
   means: truncated subtraction in ℕ, `x / 0 = 0`, `Real.log` of negative
   numbers, `deriv` where there is no derivative, `riemannZeta 1`.
2. *Definition.* A Mathlib definition does not mean what its name suggests
   (§1, point 2). Rare, but with the largest reach (§13.7).

*Proposed:*
- **Use: in every class-A ticket, complete.** The ticket lists the Mathlib
  definitions its statement uses directly, with their definition, docstring
  and known conventions, and question 2 names them. A catalogue of conventions
  per Mathlib definition feeds these notes; it grows from Mathlib tickets,
  findings and discussions (§8.9). Implemented (2026-11-15): under the
  statement, every ticket lists the library definitions it relies on, with
  type, docstring and the convention to know, conventions first. Notation and
  coercion plumbing (operators, numerals, pairs, inclusions) is left out; it
  stays in the glossary. Question 2 names the definitions. The catalogue holds
  notes for 16 functions, each with the Mathlib lemma that states it, and is
  applied when a ticket is served, so earlier tickets get new notes. The list is
  computed from the view shown, so a planted copy lists what it uses. Still
  open: the definition body of each library definition.
- **Definitions: by weighted sampling (§14 made concrete).** The Mathlib
  definitions in TCB(t) ∩ M of submitted results become Mathlib tickets, drawn
  with weights as in §7.1:
  - how many class-A statements use them directly (reach);
  - how close they are to those statements (direct use first);
  - whether they carry conventions (junk values);
  - the priority of the submissions that use them (C-28).

  A decision holds for the pair (definition, Mathlib version) and is reused by
  every submission on that version as long as the definition's hash is
  unchanged.
- **Planted errors in Mathlib tickets** can be looked up in Mathlib's sources
  even more easily than in a repository (§15). Trust earned on Mathlib tickets
  therefore counts for class A at most capped. Mathlib tickets are measured
  mainly through the PVV and through definition tests (§5.2).
- **Findings** go the way of §13.7: confirmed by the PVV, coordinated with
  Mathlib's maintainers, as an issue or PR with the reach analysis.
- **Report.** What a result relies on is listed, not hidden (C-29): the
  Mathlib definitions its statements use, and whether each was reviewed.
  PRL 3 keeps its meaning (TCB_new complete); "Mathlib definitions used: k of m
  reviewed" is reported next to it.

*Evidence:* QRH case study (`docs/case-studies/quasi-riemann.md`):
|TCB_new| = 1, and the meaning of the statement lies entirely in Mathlib.
Walkthrough with the project owner (2026-11-14).

### C-28 · §1, §10.3 The map, §11, §16 — Breadth first, then depth · new
*Proposed:* The aim is not only to check the best-known results but many of
them, as many as capacity allows. §1 counts 722 manuscripts from one model,
162 of them with a Lean formalization. Full class-A coverage for each of them
is out of reach, so the review proceeds in stages:
1. **Ingest, automatic, every submission:** build, axioms, kernel replay, TCB,
   mutants. Result: PRL 1, without any reviewer.
2. **Triage, sampled, every submission:** the main theorem, a weighted sample
   of its class-A declarations, and a sample of the Mathlib definitions its
   statement uses (C-27). Planted copies as usual. The result is an early
   signal: findings, and an estimate labelled "sampled", not PRL 2 or 3.
3. **Depth, by priority:** promising submissions get full class A (PRL 2–3),
   then the Mathlib definitions they rely on (C-27), then class-B sampling
   (PRL 4). Priority comes from:
   - interest ψ (§10.2);
   - reach: how many results build on it (PRL_eff, §10.1);
   - triage findings: a finding raises priority, since someone has to decide
     or fix it;
   - the map (§10.3): high attention and low PRL first.

   Priority does not come from votes (C-26).

Over time this pushes promising results up the PRL ladder, while the "Halde
aus der KI-Flut" (§10.3) is at least triaged. A dangerous result is then
noticed before others build on it.

*Consequences:*
- Class A keeps its 100 % rule for PRL 3 (§3). Triage reuses the same tickets
  and the same planted errors; it only changes the order.
- The order is a weight in the choice-set draw (SR-38): triage tickets of
  submissions not yet triaged first, then full class A of submissions by
  priority.
- The progress page and the reports show the stage of every submission
  (ingested, triaged, in depth) and label sampled results as such.

*Evidence:* Walkthrough with the project owner (2026-11-14).

### C-29 · §2.2, §15 — Checking the trusted base · refine
*Current:* The toolchain and the official packages (H) are trusted, and so is
the kernel. The kernel replay (C-18) covers every other module.
*Proposed:*
- **Replay the official packages** through the kernel once per pinned version
  (Lean's `--fresh` mode). It takes hours, but the result is shared by every
  submission on that version. Until then the report says: "Mathlib at
  `<commit>`, from the official cache, trusted as far as Mathlib's CI".
- **An independent second kernel** (e.g. nanoda, lean4lean) re-checks the
  replayed modules, as a guard against bugs in Lean's kernel.
- **Trusted assumptions in the report and on the progress page:** kernel
  version, library versions and whether they were replayed, and the library
  definitions the statements use with their review status (C-27).

*Evidence:* ADR 0009, "What the replay does not cover"; QRH: 4 101
official-package modules were trusted by location, not replayed.
*Implemented in part (2026-11-15):* the same principle for a repository's own
modules. `dpc ingest-batch` ingests several main theorems of one commit with
one fetch, one snapshot and one kernel replay over all their import closures;
build and analysis run per theorem, and each theorem records the part of the
shared replay its declarations live in.

### C-30 · §3 question 2, C-27 — Conventions that depend on the instance · refine
*Current:* C-27 notes conventions per library constant (`dpc/tickets/notes.py`).
The glossary leaves instances out (`lean/analyzer/DpcAnalyzer/Render.lean`,
`isInstance`), and the rendering hides instance arguments.
*Problem:* Some meanings are fixed not by the constant but by the instance that
elaboration resolves. `‖x‖` is `Norm.norm` either way, but on `Fin 3 → ℝ` and on
`ℝ × ℝ` Mathlib's norm is the sup norm, on `EuclideanSpace ℝ (Fin 3)` the
Euclidean one. The same holds for the distance, and for the order on products
and functions (componentwise). All of this is Mathlib, so it lies outside
TCB_new, and neither the glossary nor the notes show it. A reviewer who does
not know the convention reads `‖u x‖` as the Euclidean norm.
*Proposed:*
- For constants whose meaning depends on an instance (norm, distance, inner
  product, order, measure, topology), the ticket names the type the instance
  was resolved on, and the convention where one is known, e.g. "‖·‖ on
  `Fin 3 → ℝ`: sup norm", with the Mathlib lemma that states it.
- The convention catalogue of C-27 is keyed by constant *and* carrier type,
  not by constant alone.
- A mutation operator that swaps the carrier (`EuclideanSpace ℝ (Fin n)` ↔
  `Fin n → ℝ`) measures whether reviewers notice.

*Evidence:* `Render.lean` skips instances; `notes.py` is keyed by name.
Whether the Navier–Stokes case study is affected depends on the carrier type
of its velocity field; not checked yet. Walkthrough with the project owner
(2026-11-15).

### C-31 · §2, §8.8 / OS-3, §11 — The choice of T and the claims of the paper · new
*Current:* Everything is computed from the main theorem T, and the submission
names T. Class A checks that T says what its mapped passage says (ADR 0012).
*Problem:* If the repository formalizes only part of the paper (a special
case, a lemma instead of the main theorem, one of three main results),
TCB_new is computed correctly from T, every ticket can be decided correct, and
the paper's main claim is still unchecked. The fidelity review catches this
only if T is mapped to the main claim: T mapped to Lemma 3 is reviewed against
Lemma 3. ADR 0012 has no rule for claims of the paper without a counterpart in
Lean.
*Proposed:*
- **The claims of the paper come first.** When a submission is opened, a
  maintainer (later a mapping ticket, OS-3) lists the main claims of the paper,
  each with its passage: the theorems and corollaries the abstract or
  introduction states. Each claim is mapped to a declaration or marked "not
  formalized".
- **A claim without a counterpart is a finding,** not an omission. The report
  states "claims formalized: k of m" next to the PRL and names the missing
  ones. PRL 3 applies to the formalized claims and says so.
- **The mapping can be contested** as in ADR 0012, with a new reason: "this is
  not the claim of the paper" (T is a special case, or the main claim is
  elsewhere).
- Several main theorems per submission are already possible
  (`dpc ingest-batch`, C-29).

*Evidence:* `dpc/analysis/tcb.py` computes everything from T; ADR 0012 has no
rule for unmapped claims. Walkthrough with the project owner (2026-11-15).

### C-32 · §10.2, §9.4, SR-38, C-22 — Fit and motivation without opening the draw to steering · new
*Aim (project owner, 2026-11-15):* reviewers should find tickets that suit
them, and should neither despair, feel lost nor be bored. Nobody masters every
field. This must not weaken what makes the platform sound.

*Fixed, not negotiable:*
- No assignment of persons to tickets, no free choice of a paper or ticket,
  no catalogue to pick from (§9.4, §10.2, SR-38).
- Round 1 is blind; a chain counts as one vote (§8.6, §9.4).
- Planted errors are spread over all tiers and revealed late (§8.2, §8.9).
- Interest ψ never decides whether class A is reviewed (§10.5).
- **The rule behind everything below:** the draw may only use features a
  planted copy inherits from its original: paper, domain, tier. Then the
  estimates of trust, the decision rule and ψ stay unbiased.

*Problem: rerolling is steering.* Let τ be the factor by which an account is
offered a given ticket more often than under a uniform draw. Before this
proposal a set stayed valid for an hour, up to 24 sets a day could be drawn,
and every change of preferences discarded the current set at once
(`State._on_reviewer_preferences_set`). An account could burn its 24 draws
within minutes and see about 96 tickets a day. Taking a ticket and returning
it gave a further set that no limit counted. τ follows from the limits:
τ = N·(1 − (1 − n/N)^m) for N open tickets, sets of n and m sets seen per
ticket taken. Choosing alone gives τ = n = 4, since an attacker takes its
target whenever a set shows it; with 24 sets a day and one ticket taken,
τ ≈ 79 (N = 200). Narrow preferences multiply τ further.

Why τ matters, as an illustration: a wrong result passes only if every one of
the k_min + 1 = 4 parallel slots of a ticket is held by the attacker, since
one honest finding blocks. With s attacking accounts among H honest ones,
P(captured) ≈ (τ·s / (τ·s + H))⁴. For s = 5, H = 40: τ = 1 gives 0.015 %,
τ ≈ 6 gives about 3 %, τ ≈ 25 about 33 %. The simulation agrees for τ = 1
(5 against 40: 0 %; 40 against 10: 71 %). The formula leaves out three things
that change the numbers: new accounts carry no weight in the decision rule
(ŝ = ĉ = 0.5) until planted errors reveal them; honest reviewers also miss
errors; and PVV samples and claims intervene. Accounts gain weight cheaply
where planted errors can be looked up (C-07), so identity is the actual
defence (C-34), and the parameters below must come from the simulation.

*Implemented (2026-11-15), safe without the simulation:*
- **Unused sets are limited, reviewing is not.** At most 6 sets per 24 hours
  may lead to no review: expired or discarded by a change of preferences
  without a ticket taken, or whose ticket was given back or lapsed (taking and
  returning would otherwise be an uncounted reroll; this limits looks, not
  trust). Sets drawn while the reviewer holds as many tickets as allowed do
  not count; nothing could be taken from them (`choice_set.drawn` records
  `at_limit`). The cap of 24 sets in all stays. A plain cut from 24 to 6 sets
  would stop diligent reviewers: every ticket taken uses up a set. Parameters
  `max_unused_sets_per_day`, `max_choice_sets_per_day`. With these limits τ
  is at most about 26 (6 unused sets, one ticket a day) and about 8 when every
  ticket taken costs one unused set.
- **Preferences can change 3 times a day** (`max_preference_changes_per_day`),
  since each change is a reroll. Saving unchanged preferences changes nothing
  and draws no new set.
- **Maintainers are exempt** from both limits: they are appointed, not
  anonymous accounts, and they test. The limits count the last 24 hours, so
  at their introduction they also counted the day's earlier sets; the project
  owner, a maintainer, met them in the walkthrough at once.
- **A reached limit is not an error.** The client says when the next set
  comes ("tomorrow at 15:33") and how many changes of preferences are left
  today; `POST /api/choice-set` returns `limit` with reason and time,
  `GET /api/me` returns `preference_changes_left` and `preference_change_at`.
- **Preferences at sign-up, optional,** for domains. The form says that a
  preference is not a qualification: it only raises the chance, trust comes
  from the work, harder tiers open with experience. Nothing selected means
  anything. Difficulty is chosen later, once tiers open.
- Earlier the same day: difficulty as an upper bound and the notice when
  preferences could not be used (C-22).

*Simulation (2026-11-15, `docs/simulation/steering.md`):* 40 honest
reviewers, one attacker whose accounts gain trust by looking up planted
errors; share of the attacker's target errors accepted (other errors: about
1 % missed):

| accounts | τ = 1 | τ = 4 | τ = 8 | τ = 26 | τ = 79 |
|---|---|---|---|---|---|
| 5, full weight | 4 % | 8 % | 13 % | 22 % | 45 % |
| 10, full weight | 9 % | 30 % | 55 % | 82 % | 94 % |
| 10, identity weight 0.5 | 3 % | 1 % | 5 % | 4 % | 3 % |

Findings: the limits on rerolling lower τ (79 → at most 26) but cannot bring
it near 1, because choosing is itself a lever. What stops the attack is the
accounts' weight: shrinking it halfway for weakly identified accounts keeps
target success at or below 5 % for every τ, at 0.2–0.8 more reviews per item.
So the decisive levers are identity (C-34) and planted errors that cannot be
looked up (C-07), not parameters of the draw. A bound τ_max of 2–3 on
preferences is small next to the τ of choosing; it keeps preferences from
adding to it. The model shrinks only the attackers' weight; if every weakly
identified account starts with less weight, the cost in reviews is higher.

*Proposed, after the simulation (D below):*
- **A bound τ_max instead of `pref_min_papers = 2`.** Preferences may raise
  how often one paper is offered to a person by at most τ_max (about 2–3)
  over the uniform draw; the minimum number of matching papers follows from
  it. If too few papers match, the preference widens: first only the domain,
  then none. Within the bound, up to 3 of 4 slots may match; at least one
  slot stays random.
- **Preferences for everyone, newcomers included.** Newcomers are those who
  most need a fitting start, and their verdicts carry no weight yet. A trust
  threshold for preferences protects little; the bound τ_max and identity
  (C-34) do. Weight, not preference, depends on identity.
- **Preferences never filter.** Hard limits come only from the exclusion
  rules and locked tiers (SR-32).

*Not now, decide:* "staying with a paper". The next set may hold one or two
further tickets of the paper someone just reviewed, capped at about 25 % of
the paper's class-A declarations per person. It saves the costly switch of
context, but one person's misreadings then repeat across tickets. Decide
after the simulation shows how much such correlated errors weigh.

*D. Order:* (1) the safe limits above — done; (2) extend the simulation
(`dpc/sim`: steering factor τ, weight by identity) and run a grid over the
number of accounts, τ and the weight — done, see above; (3) next, by the
result: a graded start by identity (C-34), then τ_max, domain per paper
(C-37), rerouting (C-33); (4) partial votes, implicit preferences with consent
and platform metrics (C-36), preferences and choice data in the vault (C-35).
The full simulation of choice sets with preferences, rather than through τ,
is still to do; it is needed to fix τ_max.

*Evidence:* `Coordinator.choice_set`, `Coordinator.unused_sets`,
`Coordinator.set_preferences`; tests
`test_sets_left_unused_are_limited_taking_tickets_is_not`,
`test_sets_drawn_at_the_work_in_progress_limit_never_count`,
`test_preference_changes_are_limited_because_each_one_rerolls`,
`test_preferences_can_be_given_at_sign_up`; `docs/simulation/README.md`
(Sybil rows). Conversation with the project owner, 2026-11-15.

### C-33 · §9.4, SR-31 — Rerouting in the pilot; partial votes later · refine
*Current:* hand-overs (§9.4, SR-31) are planned for M6. A ticket is done whole
or not at all.
*Problem:* that is the main source of feeling lost. Someone who can check the
junk values but not the function space has only "return".
*Proposed:*
- **Rerouting (hand-over type 3) in the pilot:** "needs PDE" returns the
  ticket with a domain suggestion. Several such suggestions, or a
  maintainer, correct the ticket's domain (C-37). It is a return with
  information, cheap to build, and needs no change to the decision rule.
- **Partial votes (type 2) later:** "junk values checked, the function space
  needs someone else" as a vote on some questions only. Verdicts are already
  recorded per question (C-23), but the decision rule decides per ticket:
  a ticket would be decided only once every question has enough weight. Model
  and simulate this first.
- Lenses (§8.4) stay later.

*Evidence:* `failed` per question in `review.submitted` (C-23); SR-31 in
`requirements/sr.yaml`.

### C-34 · §6.5, SR-41, FMEA R6 — Identity is the defence against fake accounts · refine
*Problem:* the simulation's finding is "the Sybil defence is identity, not
statistics". Steering by rerolling (C-32) and cheap trust by lookup (C-07)
make fake accounts worth more.
*Proposed:*
- One person, one account (SR-41). Prefer university sign-in through
  Keycloak brokering to Shibboleth (DFN-AAI, eduGAIN), and linked profiles
  (ORCID, GitHub, MathOverflow), each linkable once (C-24).
- E-mail alone is nearly worthless. A phone number only as a keyed hash
  (HMAC with a secret key in the vault), never the number and never a plain
  hash: with about 10¹⁰ possible numbers a plain hash is reversed in minutes.
  Better none.
- **Graded start by identity strength:** a strong identity starts normally;
  e-mail only gets more entry planted errors, less initial weight (cap a_max
  of §6.5) and slower growth of weight.
- **Monitoring** (maintainers, aggregated): how often an account is offered
  and takes a paper compared with expectation; accounts created in a burst
  with identical preferences; pairs with conspicuous agreement
  (`dpc/domain/anomaly.py`).

*Evidence:* `docs/simulation/README.md` (Sybil rows); C-24.

### C-35 · §12.8, SR-17 — Preferences and choice data: public log or vault · decide
*Current:* `reviewer.preferences_set`, `choice_set.drawn` and `lease.granted`
stand in the public audit log under the random id.
*Problem:* combinations such as "number theory + excellence + expert" can
identify a person, and from sets and choices implicit preferences can be
computed (profiling, GDPR). On the other hand, the log is how anyone checks
that the draw was fair and that ψ is right (SR-17).
*Proposed:*
- Preferences into the vault (the state reads them from there, as it reads
  pseudonyms).
- For sets and choices, one of: (a) only aggregated ψ public, details in the
  vault; (b) public commitments (hashes) of each draw and choice, the plain
  data in the vault, opened for an audit; (c) as today. (b) keeps the
  fairness check possible without publishing profiles.
- To be decided together with the open question whether choice data fall
  under the open licence of the reviews (§12.8).

*Evidence:* `dpc/coord/events.py` (`PreferencesSet`, `ChoiceSetDrawn`);
ADR 0008 (the log is published with the report).

### C-36 · §10.2, §10.4 — Explicit and implicit preferences; platform metrics · new
*Proposed:*
- **Explicit** is what a person states; it may raise chances (C-32).
- **Implicit** follows from Plackett–Luce per person (conditioned on the sets
  offered), from returns and from trust per domain. It is profiling: shown
  only to the person, only if they switch it on, as the talent signal of
  §10.4. Use: suggestions ("add combinatorics?") and a warning of overload
  (asks for Hard, returns most of it).
- **Implicit preferences never steer the draw:** that would be a filter bubble
  and a hidden way to target papers.
- **Platform metrics, aggregated only:** how often a choice matches the
  chooser's preferences; how often tickets are returned inside and outside
  them; how both develop over time; and the health check of C-22, how often
  planted copies are chosen compared with real tickets of the same sets.

### C-37 · §9.2, SR-04 — Domain per paper, in names mathematicians know · refine
*Current:* a heuristic per declaration from the Mathlib areas a statement
uses. It put a paper on Jacobsthal's function under "algebra" and left the
Seymour paper "general".
*Proposed:*
- The domain is set per paper, from its arXiv category or MSC class, and
  shown in MSC terms ("Partial differential equations", not "analysis").
  A maintainer can correct it per declaration (SR-04), also after the
  submission is open; today there is no event for that.
- Rerouting (C-33) feeds corrections back.
*Implemented in part (2026-11-15):* where a repository files its modules by
area (`OAI.Combinatorics.…`, `OAI.NumberTheory.…`), that area now comes before
the Mathlib areas (`dpc/analysis/domains.py`, source "module"). For openai/math
this is in effect one domain per paper.

### C-38 · §8.10 — Recognition grows with difficulty · refine
*Proposed:* acknowledgement and bonuses grow with the tier of a ticket.
Otherwise hard tickets are avoided once preferences make easy ones easy to
find, and the hardest tickets wait longest.

### C-39 · §3, §8.8, §16 step 3, SR-21, SR-24 — Class-A tickets that can be checked · refine
*Problem (walkthrough with the project owner, 2026-11-15):* the Erdős 970
ticket `OAI.Erdos970.Erdos970Final.erdos_970_quadratic` could not be
checked. Its statement is only the name `…Targets.JacobsthalQuadratic`; the
glossary gave its type `Prop`, "Builds on" gave names, no passage was mapped,
and the tier said "easy". The content sat in two other tickets
(`JacobsthalQuadratic`, `IsJacobsthalBound`). Concept §3 asks for the
definitions a statement uses, the passage and the neighbours in the graph,
§8.8 for unfolding definitions, SR-21 for go-to-definition (S-14: not built).

*The rule for everything below:* a planted copy may stand out only in ways a
real error can. A real error is a false statement whose proof the kernel
checked: everything proven fits it. For a mutant, everything proven fits the
original. So every aid must be producible for the mutant in the same way, and
nothing proven that mentions the reviewed declaration is shown during class
A: not its proof, not the lemmas using it with their statements and names
(`…_lt_iff` gives the relation away). Otherwise "does the proof fit the
statement?" finds planted copies without mathematics. Definitions and Mathlib
are safe: definitions are not proven (a planted copy shows its mutant there),
and Mathlib is the same for every ticket. A meaning in words stays absent on
purpose: it would be a back-translation, only after round 1 (SR-36); the
passage gives the meaning, and comparing the two is the review.

*Implemented (2026-11-15):*
- **Unfolding and go-to-definition.** Under the statement, "Builds on" and
  "Used by" list the class-A declarations of the submission; each unfolds on
  request, level by level down to Lean and Mathlib, in the plain rendering,
  with only the conventions to know (the rest on hover). The main theorem is
  marked; a folded map lists all declarations of the formalization. Only
  units of TCB_new appear (definitions, structures, the main theorem's
  statement), never a lemma of class B. Server side: `GET
  /api/leases/<id>/context` (names, kinds, edges), `POST
  /api/leases/<id>/unfold` (one view).
- **One version per person** (added in the implementation). Unfolding the
  original of a declaration D in one ticket would give away D's planted copy
  in a later ticket, by comparison; and someone who reviewed D's copy would
  learn from unfolding D elsewhere that it was a copy, before the batch
  reveal. So every person sees every declaration in one version: the one of
  their own ticket (a planted copy included) if they had one, otherwise the
  original, recorded as `unit.shown`, after which D is not offered to them as
  a ticket. The ticket says so next to the unfolding.
- **The main theorem needs its passage:** `open-submission` refuses a
  submission without one (§16 step 3, SR-24, ADR 0012). Without a common
  passage every reviewer compares with another place, and the k_min votes do
  not answer the same question. Other declarations may be mapped later.
  Passages for Erdős 970 and Seymour are written for the walkthrough, as
  paraphrases.
- **The tier is measured on the unfolded statement** (`tier_of_unfolded`):
  the statement with every declaration it builds on. A one-name statement is
  no longer "easy".
- **Hover for chained field notation** looks up every link
  (`n.primeFactors.card`, `(a + i).natAbs.Coprime n`).
- **Conventions:** `Nat.Coprime` (0 is coprime only to 1,
  `Nat.coprime_zero_left`), `Nat.primeFactors` (none for 0 and 1,
  `Nat.primeFactors_zero`, `Nat.primeFactors_one`); checked against Lean
  4.34.1 and Mathlib d13f23b7.
- **No repository link in the ticket header**, cosmetically: the name is
  enough to search, but the platform should not invite a comparison. The
  submission page keeps it.
- Docstrings of the submission's constants are empty because the source has
  none (openai/math, `Model.lean`), not because rendering drops them.

*Added (2026-11-16):*
- **Statements laid out for reading** (`web/src/layout.ts`). Lean's printer
  nests every `∧`, `∀` and `→` one level deeper; a long statement
  (`OAI.MemoryPrecision.main`: ten conjuncts) became a staircase. The page
  lays the same text out again: conjuncts one below the other, each `∀` with
  its hypotheses on one line, the conclusion indented. Only whitespace
  changes, checked by the function itself; originals and planted copies pass
  through the same function, so it obeys the rule above. Lean's own line
  breaks are one click away.
- **A submission opened again replaces the closed one** on the progress page
  (same repository, commit and main theorem). Until the event for correcting
  passages exists (below), closing and opening again is how a passage is
  fixed; the earlier version keeps its record.

*Still open (covered by the specification, not built yet):*
- For Lean and Mathlib constants, their definition on request, one level
  deep, or a link to the Mathlib documentation. For junk values the
  definition counts, not the docstring. The hosted documentation shows only
  the current Mathlib: build it for the pinned version, or link with a note.
- The declaration's own docstring (§3). Borderline: a contradiction with the
  docstring also occurs for real errors, probably more often for planted
  copies; measure in the pilot how often they are found that way.
- Source with proofs after the batch reveal (§8.9, SR-37), on the progress
  page and in the discussions: from the reveal date, not right after one's
  own verdict.
- A later event for maintainers to map or correct a passage of an open
  submission; today passages are set when it is opened.

*Pilot measures:* returns, time per ticket and agreement between reviewers;
planted errors found per mutation kind and via the docstring; share of
justifications that cite the passage; A/B with and without unfolding and
passage. Acceptance test: Erdős 970, the whole statement with its passage on
one screen, every name in it looked up, `primeFactors` and `natAbs`
included.

*Evidence:* `TicketContext`, `Coordinator.context_map`, `Coordinator.unfold`,
`tier_of_unfolded`, `require_main_passage`; tests
`test_unfolding_shows_each_unit_in_one_version_per_person`,
`test_whoever_holds_a_planted_copy_unfolds_it_as_the_copy`,
`test_a_statement_that_is_a_single_name_is_measured_unfolded`,
`test_the_main_theorem_needs_its_passage_before_review`.

### C-40 · I-3, §15 — No proof in class A during review · refine
*Current:* interface I-3 lists `source_lean` for class-A tickets; §15 assumes
that comparing with the repository costs about as much as a review.
*Proposed:* remove `source_lean` from class A during review and state the
rule of C-39 instead (ADR 0008 already deviates so). In the threat table of
§15, drop the assumption: comparing takes about a minute and also tells which
tickets are real (ADR 0006, simulation: lookup attackers earn more trust than
honest reviewers).

### C-41 · ADR 0006, §8.2 — More kinds of planted errors and of tickets · decide
Each of the following needs the project owner's decision:
- **Theorems that only confirm a name** (decide). If the type of a theorem
  is exactly one `Prop` constant of the submission, it joins the unit of that
  definition (`dpc/analysis/tcb.py`, `units()`). SR-05 still holds (every
  declaration in exactly one ticket). It departs slightly from §3 ("one
  declaration"), but units already group auxiliary declarations; without it,
  four people check the same content twice.
- **Planted errors on the paper side** (decide; ADR 0006 option 2): the Lean
  stays genuine, the passage is changed subtly. Its proof fits its statement,
  as for a real fidelity error, so it obeys the rule of C-39 even with proofs
  visible. Conditions: every passage is paraphrased uniformly, no verbatim
  quotes (otherwise the arXiv PDF exposes the change); a person confirms every
  change as really different (there is no automatic equivalence filter for
  text). Gap: docstrings that quote the paper expose them too.
- **Visibility by kind of ticket** (decide), building on the mixed form of SE
  §8.3: fidelity tickets (experts) with planted errors on the paper side only,
  proofs and source visible; question tickets for everyone (junk values,
  vacuity, edge cases) with Lean mutants and no proofs. Everybody knows the
  kind, and both kinds carry the same share of planted errors, so visibility
  tells nothing.
- **Proofs during review** (decide): not for now; decide again after the
  pilot, with data on how well planted errors are disguised (AS-5).
- **Class B:** how planted errors should look there is open; with proofs
  visible, Lean mutants are recognised at once.
- *Later:* `#eval` examples and a search for counterexamples (§8.8) need the
  mutant built in the sandbox as well (SR-20); expensive.

### C-42 · §6.3, §6.4, §8.5, SR-04, SR-13, SR-24, SR-35, ADR 0010 — Roles: earned and appointed, kept apart · new
*Problem (walkthrough, 2026-11-16):* one role, *maintainer*, combined running
the platform, curating content, moderating and arbitrating, and it counted as
PV and PVV in every domain. Three consequences:
- A maintainer sees the original of every declaration under review (maintainer
  view). As PVV the same person confirmed error claims, and could tell a
  planted copy from the original by comparison instead of by mathematics: the
  case C-39 rules out for everyone else ("one version per person").
- A maintainer without competence in a domain confirmed findings there.
- Escalations were decided by one person; paper passages had no procedure and
  could only be fixed by closing and opening the submission again.

*Decided (project owner, 2026-11-16): five roles on two ladders.*

```
  Administrator        platform · appointed · few
        │ appoints
  Maintainer           per domain · appointed · requires PVV there
        │ requires
  ┌─ earned, measured per domain (trust κ) ─┐
  PVV                  κ ≥ θ_PVV
  PV                   κ ≥ θ_PV
  Reviewer             everyone after sign-up
```

| | Reviewer | PV | PVV | Maintainer | Administrator |
|---|---|---|---|---|---|
| Review tickets, discuss | ✓ | ✓ | ✓ | ✓¹ | — |
| Vote with weight | little | ✓ | ✓ | ✓¹ | — |
| Re-checks, confirming error claims | | | ✓ | ✓¹ | — |
| Propose passages, hashtags, domain corrections | | | ✓ | ✓ | |
| Confirm them (second pair of eyes) | | | | ✓ | |
| Decide escalations (panel of three, blind, majority) | | | | ✓ | |
| Reopen requests, moderation in the domain | | | | ✓ | |
| Open and close submissions, parameters | | | | | ✓ |
| Appoint and revoke maintainers (public, with reason and term) | | | | | ✓ |
| Vault: which tickets are planted | | | | | ✓ |

¹ Only with the trust the person earned there, never by appointment; not on a
declaration whose original they saw as maintainer.

*Rules:*
1. **Who knows the internals of review does not review.** Administrators
   (vault, closing, parameters) take no tickets and no PVV duties and sit on
   no panel. A maintainer who saw the original of a declaration under review
   (maintainer view, mapping a passage) is recorded as having seen it
   (`unit.shown`, C-39) and is not offered its tickets.
2. **Voting weight comes from measurement only.** An appointment gives tasks,
   not weight: a maintainer for number theory counts in a PDE review with the
   trust measured there. Exception, the cold start: an administrator may
   appoint *founding maintainers* of a domain, with a reason and an end date;
   until that date they count as PVV in that domain, because nobody can have
   earned PVV in a new installation. After it, only measured trust counts.
3. **Content needs four eyes.** A PVV or maintainer of the domain proposes a
   passage (or a domain correction); another maintainer of the domain
   confirms it. So PVVs work on tickets without being maintainers. Passages
   of an open submission can be mapped this way while no review of the
   declaration exists; afterwards only by opening the submission again.
4. **Escalations are never decided by one person**, but by a panel of three
   maintainers of the domain, each voting blind, by majority, each with a
   reason. Authors, members of the submitting lab and earlier participants of
   the ticket are excluded (SR-08, SR-50).
5. **Submitting is not a rung but a permission beside the ladder.** Anyone with
   a strong identity (C-34) may submit their own work; an administrator opens
   it, and the submitter becomes an author who does not review it (SR-08).
6. **Courses** (C-43) have a course lead, a maintainer-like role scoped to one
   course instead of a domain.

Every appointment and revocation is an event in the public log, with reason
and term; maintainers are appointed per domain and only if they are PVV there
(or founding). The identity provider grants only the administrator role (ADR
0010); maintainers are appointed in the platform, because only the platform
knows domains and trust.

*Migration:* the former global maintainer becomes the administrator (the
events `reviewer.maintainer_appointed` and `…_revoked` of existing logs are
read as such; new logs write `reviewer.admin_appointed` and `…_revoked`).
Maintainers of domains are appointed anew, if needed as founding maintainers.

*Implemented (2026-11-16):*
- **Step 1, the roles apart.** Administrator (`reviewer.admin_appointed`) and
  maintainer per domain (`role.maintainer_appointed` with domains, reason,
  end date, `founding`); nobody is PVV by appointment except founding
  maintainers until their end date; administrators take no tickets and no PVV
  duties; maintainers act only in their domains (escalations, reopen
  requests, moderation, notes, hashtags, contested mappings). The maintainer
  view of a declaration under review records `unit.shown`; whoever re-checked
  an original may not resolve the claim on its planted copy. CLI `appoint`,
  `appoint-maintainer`, `revoke-maintainer`; an administration page with
  appointments and a maintenance page per domain.
- **Step 2, passages by four eyes.** `passage.proposed` by a PVV or maintainer
  of the domain, `passage.decided` by another maintainer of it; confirmed, the
  passage applies to every ticket of the declaration, planted copies
  included, and clears old contests. Only while nobody has reviewed the
  declaration. Proposer and confirmer are recorded as having seen it.
- **Root testers** for test systems: every role, free of the rules (limits,
  tiers, one version per person, the separation above), but never twice on a
  ticket. Effective only where the parameters set `root_accounts`
  (walkthrough, demo, click dummy), never in production; appointed by the
  operator (`dpc appoint-root`) as `reviewer.root_appointed`.

*Why reviewers do not vote on passages* (asked in the walkthrough): a vote
during review would change the reference while verdicts are being given;
the k_min votes of a declaration would compare with different passages, and
the first votes would anchor the later ones. The vote on a passage is
therefore the confirmation by a second maintainer before the first review;
afterwards reviewers contest a passage (SR-24), and a maintainer can open the
submission again. Planted errors are unaffected: original and copy carry the
same passage, so the passage tells nothing about a ticket.

*Still open:* step 3, the panel of three for escalations (today one
maintainer of the domain decides); identity strength as a condition for
appointments (C-34); submitting through the web (C-45).

*Evidence:* `tests/test_roles.py`, `tests/test_passages.py`;
`Coordinator.appoint_maintainer`, `maintainer_view`, `propose_passage`,
`decide_passage`, `appoint_root`.

### C-43 · §6, §6.5, §10, §12.8, SR-08, SR-41, SR-50 — Courses: students review during a semester · new
*Idea (project owner, 2026-11-16):* a lecturer (Dr, PhD) runs a course on the
platform; during the semester the students review a few tickets that belong
to the course's subject.

*Why it fits:* a class-A ticket is an exercise in reading a formal statement
against the paper, which is what a course on formal mathematics teaches.
Planted errors give each student objective feedback after the batch reveal.
Students sign in through their university and so bring a strong identity
(C-34). Courses bring reviewers to the domains that lack them.

*Where it meets the mechanism, and what is proposed:*
- **Course lead, not maintainer.** Maintainers see declarations under review,
  planted copies included (C-39, maintainer view). A lecturer with that view
  could tell students, even without meaning to, which of their tickets are
  planted. Proposed: a separate role *course lead*, confirmed by a maintainer,
  only with a strong identity (C-34). The course lead sees who in the course
  took part and how many reviews each made; after the batch reveal, also
  their verdicts, reasons and the planted errors they met and found. The
  course lead does not see tickets under review, the vault or other
  reviewers' votes. The role is scoped to one course; it belongs in the role
  hierarchy announced as C-42 (an axis "scope": platform or course).
- **One student of a course per ticket.** Students of one course talk to each
  other and hear the same explanations in the tutorial. Their votes on one
  ticket are not independent, but the decision rule assumes they are (§6).
  Proposed: at most one member of a course per ticket, checked like the
  conflicts of interest of SR-08. Membership is a group in the vault, like an
  affiliation (SR-50), and does not appear in the public log. Monitoring of
  pairs that agree conspicuously often (C-34) covers what remains.
- **A pool, not assignments.** The course lead chooses a pool: one or more
  submissions or domains, and a range of tiers. Students draw choice sets
  inside the pool as everyone does (C-32). The course lead never assigns
  single tickets; otherwise a course becomes a way to target tickets. If the
  pool runs out, students draw from all tickets as usual.
- **Weight as for anyone.** Students start with the weight their identity
  gives (C-34), entry planted errors included, and gain trust by measured
  reliability like every reviewer. Optionally a practice mode first: decided
  tickets with known answers, not counted, then live tickets.
- **No grades from the platform.** Grading on verdicts would reward agreeing
  with the majority and punish reporting an error. The course lead gets
  participation, reasons and the planted errors met and found as feedback;
  credit for the course is the lecturer's decision, outside the platform.
- **Privacy.** The link between pseudonym and student, needed for course
  credit, stays in the vault, with the student's consent, readable only by
  the course lead. The public log knows the random id and not the course.
  A student can leave the course; their reviews remain under the open licence
  (§12.8) without the link to the course.
- **Semester.** A course has a start and an end. Leases still open at the end
  are returned without counting against the student. The pool has to hold
  enough open tickets: a course of 30 students with three tickets each needs
  about 90 reviews; the 18 openai/math papers of the walkthrough hold 266
  units.

*Order:* after C-34 (identity strength) and C-42 (role hierarchy). Then a
course is a scoped role plus a group: events for creating a course, joining
and leaving it (membership in the vault), the pool as a parameter of the
draw, and the one-per-course rule in the eligibility check
(`Coordinator.why_not`).

*Pilot measures:* students against other reviewers on planted errors;
agreement inside a course against agreement across courses (is the
one-per-ticket rule enough?); returns; how often reasons cite the passage.

*Status:* proposal; nothing built.

### C-44 · §10.1, §11.1, C-25, C-26 — Hashtags for problems; filters on progress and discussions · new
*Request (project owner, 2026-11-16):* the progress page and the discussions
get filters, and the problems themselves get hashtags so that they are found
quickly.

*Proposed and implemented (2026-11-16):*
- **Hashtags per submission.** A submission, i.e. a problem, carries up to 12
  hashtags: the problem (`navier-stokes`, `erdos-problems`, `riemann-zeta`),
  a family (`millennium-prize`, `counterexample`), the subject
  (`symplectic-geometry`). Normal form: lower-case letters, digits and inner
  hyphens, 2 to 40 characters; `#Erdős Problems` becomes `erdos-problems`.
- **Who sets them.** Maintainers, when opening a submission
  (`open-submission --tag`) or later on the paper's progress page or with
  `dpc tag-submission`. Always the whole set, recorded as the event
  `submission.tagged` in the public log. Reviewers do not set tags (no
  vandalism to clean up); proposing tags for a maintainer to confirm can come
  later.
- **Not for the draw.** Hashtags serve finding a problem on the progress page
  and in the discussions. They are not a preference: a tag can name a single
  paper, and choosing tickets by paper would allow targeting them (C-32,
  C-34). Preferences stay by domain and tier.
- **Per submission, never per declaration.** A hashtag is the same for every
  ticket of the submission, planted copies included, so it tells nothing
  about a ticket. Tags per declaration would be a channel to mark tickets (a
  maintainer sees the planted copies) and are not planned.
- **Filters on the progress page:** search in titles and hashtags (`#…`
  searches hashtags only), hashtag, domain, source (owner/repository), status
  (not started, in review, complete, with findings, closed) with counts under
  the other filters, and order. A paper is filed under the domain of its main
  theorem, otherwise the most frequent domain of its declarations, so it
  appears under one domain. A submission opened again replaces the closed one
  (C-39). Hashtags on a card filter by a click.
- **Filters in the discussions:** search in declarations, papers and
  hashtags; hashtag, paper, domain, outcome (accepted, error found) with
  counts, "only where I can share my review", and order (worth reading,
  latest activity, most posts). Threads open only after the planted errors
  of their submission are revealed (C-25), so filtering by outcome tells
  nothing about planted copies.
- **What someone filters for is not recorded.** The filter state stays in the
  browser session, not in the log (no profiling, C-35).
- The hashtags of the walkthrough were suggested by the assistant; a
  maintainer has to check them.

*Open:* reviewers proposing hashtags for a maintainer to confirm; a fixed
vocabulary for subjects (MSC classes, C-37) next to free tags for problems;
hashtags in the report (SR-42).

*Evidence:* `dpc/coord/tags.py`, `Coordinator.tag_submission`,
`SubmissionTagged`, `POST /api/admin/submissions/<id>/tags`;
`web/src/components/ProgressFilters.tsx`, `DiscussionFilters.tsx`,
`Tags.tsx`; tests `tests/test_tags.py`,
`test_a_paper_is_filed_under_the_domain_of_its_main_theorem`.

### C-46 · §3, §6.4, C-21, SR-28, SR-35 — k_min counts qualified verdicts; learner seats · refine
*Problem (review of 2026-11-16):* concept §3 gives class A to the PV role,
the simulation draws only PV for it, but the coordinator opened easy and
medium tickets to everyone (C-21) and counted every review for k_min. A new
account (s = c = 0.5) carries no weight but filled a seat, so the reserve
"k_min = 3" of the parameter study did not exist: in the worst case one
account with high trust (e.g. from lookup), fresh accounts to fill the seats
and a PVV review that misses the error.

*Decided (project owner, 2026-11-16), built:*
- §6.4 reads "k_min independent **qualified** verdicts": only reviews by
  people who held the PV role in the domain when they reviewed fill k_min
  (`Vote.qualified`; the coordinator uses `ReviewRec.roles`).
- C-21 precisely: the k_min + 1 seats of a ticket are for the PV role.
  Others review on **learner seats** (`learner_slots`, default 1): their
  verdicts are evidence with their measured weight and build their trust,
  but never fill k_min. The 14-day opening of C-21 opens the tiers, not the
  seats.
- The one-finding rule stays: a justified "incorrect" of a learner blocks.
  Against blocking out of malice, a learner has **one open claim at a time**
  (`max_open_claims_learner`); further findings are deferred, do not block,
  and open when the first is decided; if their ticket was decided meanwhile,
  they go to the maintainers as reopen requests, so no finding is lost.

*Consequence:* without onboarding the cold start locks (C-48).

*Evidence:* `tests/test_qualified.py`, `tests/test_harness.py`;
`docs/simulation/README.md` (before and after).

### C-47 · §6.5, SR-41 — A cap on the prior from profiles · refine
*Problem:* `external_prior` (linked profiles, not connected yet) had a_max = 5:
α₀ = 6 gives a "correct" vote the factor 6 (about 20 lead from π₀ = 0.02 to
δ_A = 10⁻³, so two such accounts decide alone), and the lower bound of
Beta(6, 1) is 0.61: the account would be PV at once.
*Decided (2026-11-16), built:* a_max = 1. A profile moves the odds by at
most a factor 2 per vote and never makes anyone qualified; weight comes from
measurement (C-42). Identity strength weighs separately (C-34).
*Evidence:* `test_a_profile_alone_never_makes_anyone_qualified`.

### C-48 · §6.5, §8.9 — Onboarding with entry planted errors · decide
*Problem (harness, 2026-11-16):* with C-46 nobody becomes PV in a new
installation: learners get one seat per ticket, evidence arrives only with
reveals and decisions, and decisions need PV. In 45 simulated days no honest
account reached θ_PV. The parameter study never showed this because it
starts every account with eight planted errors and eight checked practice
items.
*Proposed:* an onboarding phase before the first real ticket: training
tickets with known answers (planted errors from a training pool, decided
real tickets), counted as evidence like planted errors; more of them for a
weak identity (C-34). Founding maintainers bridge the very start. Measure the
effect with the harness before deciding numbers.

### C-45 · §16, I-1, SR-05, SR-08, SR-20, SR-24, SR-50 — Submitting through the web · new
*Today:* an administrator runs the pipeline on the command line: `dpc ingest`
(or `ingest-batch`), `render`, `mutate`, `open-submission` with the submission
file of interface I-1 and the paper map. Authors are linked by hand
(`--author`). There is no web form.

*Proposed flow:*
1. **Form**, signed in with a strong identity (C-34): repository URL and
   commit, main theorem and its module, the paper (arXiv id and version, or a
   URL), authors (accounts) and lab (SR-50, stored as a tag in the vault),
   suggested domain and hashtags (C-44), and the declaration that it is the
   submitter's own work or submitted with the authors' consent. Optional: a
   challenge file naming the main theorem, as openai/math ships them
   (`ComparatorChallenges/*.json`).
2. **Pre-check**, immediate and cheap: the commit exists, the toolchain is
   supported, the size is within limits, the same repository, commit and main
   theorem are not already submitted (then a link to it).
3. **Build in the sandbox**, queued (SR-20, ADR 0005): ingest with limits on
   CPU, memory and time, kernel replay, analysis, rendering, planted-error
   candidates; batches share one replay (C-29). The submitter sees the state
   (queued, building, analysed, failed with an excerpt of the log). Quotas per
   account and lab keep the cost bounded.
4. **Review of the result by an administrator:** units of TCB_new, axioms
   (only Ax₀ admitted), replay, integrity of the official packages, number of
   candidates. Accepted or rejected with a reason, as an event.
5. **Passages before opening:** the main theorem needs its passage, proposed
   and confirmed by four eyes (C-42), by people who are not authors. Authors
   may suggest passages in the form, as hints only: choosing the passage for
   one's own formalization is a conflict of interest (an author could pick
   the passage that fits a flawed statement).
6. **Opening:** tickets with planted errors are created; authors and their lab
   are excluded automatically (SR-08, SR-50). The submitter follows the
   progress page like everyone; notifications never count tickets (tickets
   minus declarations would be the number of planted errors).

*Events:* `submission.requested`, the ingest events of the sandbox (already
in the ingest log), `submission.accepted` or `.rejected` by an administrator,
then `submission.opened`.

*Order:* after identity strength (C-34); the pipeline exists (batch ingest,
C-29), the form and the queue are new. *Status:* concept, nothing built.

### C-49 · CN-2, §12.8, SR-49 — Source-available, not open source · refine
*Decided (project owner, 2026-11-16):* the software is licensed under the
PolyForm Noncommercial License 1.0.0 (`LICENSE.md`), the documentation under
CC BY-NC 4.0 (`LICENSE-docs.txt`). The copyright stays with a single holder,
the project owner, named in `LICENSE.md`; contributions need a contributor
license agreement, which is still to be written. Commercial use needs a separate license.
*Proposed:* CN-2 reads "source-available for noncommercial use" instead of
"Open Source". Unchanged: reviews and reports produced by the system are
published under an open license (SR-49); that concerns their data, not the
software.

### C-50 · §6, §6.4, §8.9, C-25, C-46 — Review teams: alone first, then together · decide
*Request (project owner, 2026-11-19):* instead of one person per ticket, a
team of three works on a ticket together, discusses it and votes together at
the end.

*What speaks for it:* an error can be shown; whoever finds it can convince
the others, so on such tasks a team tends to reach the level of its best
member. Large tickets can be split (one reads the Lean, one the paper, one
the Mathlib definitions). People learn more and stay longer.

*Where it meets the mechanism:*
- **Independence.** §6 multiplies the evidence of k_min independent
  verdicts. Three people who talked before voting are one verdict, not
  three (the reason for "one student of a course per ticket", C-43). Counted
  as one vote, a declaration would need nine people instead of three, and
  the harness shows that three qualified ones are already scarce at the
  start (C-48).
- **Measurement.** Planted errors measure individuals. A joint verdict does
  not say who found the error; whoever goes along gains trust without
  earning it.
- **Steering.** The most confident member, or one with a purpose, can talk
  the other two out of a finding. A team chosen by its members is a channel
  for collusion.

*Proposed: alone first, then together.*
1. **The team is drawn.** A reviewer picks a ticket from the choice set
   (C-32) in team mode; the team is formed by the next two who pick the same
   ticket in team mode within a time window. Nobody chooses team mates.
   Conflicts of interest (SR-08, SR-50), the course rule (C-43) and one
   version per person (C-39) apply to every member. Members appear to each
   other as "Reviewer A, B, C" of that team only. If no team forms in the
   window, the reviewer continues alone.
2. **Own verdict first.** Each member gives verdict and reason alone, as
   today, and cannot change it afterwards. Nothing has been exchanged yet,
   so these verdicts are as independent as three solo reviews: on qualified
   seats they fill k_min, on learner seats they count as learner verdicts
   (C-46), and they alone measure trust on planted errors. A justified
   "incorrect" opens a claim at once, as today.
3. **Then the team room.** When all three have given their verdicts (or a
   missing member's lease has ended), the team sees the three verdicts and
   reasons and discusses in a private thread. It stays private; members may
   share their own part when the declaration's public thread opens (C-25).
4. **The joint verdict can add findings, never remove them.** The team ends
   with a joint verdict. An "incorrect" with a reason that none of the own
   verdicts had becomes a claim like any finding. A member's own finding
   stays even if the team is convinced otherwise; the PVV of the claim
   decides (SR-35). So the discussion can only make the review stricter.
   Apart from added findings, the joint verdict enters neither trust nor
   the decision; it is recorded for the pilot.
5. **Planted errors.** A team on a planted copy discusses the copy, like
   three reviewers who met it alone. Reveals come per member, after their
   own verdict, as today; a finding the team adds on a planted copy earns
   nobody trust.
6. **Where first.** Learner seats, courses (C-43) and onboarding (C-48),
   where no verdict fills k_min. One variant for onboarding: one PV and two
   learners; the PV's own verdict counts, the learners learn from the
   discussion. Teams on qualified seats once the pilot shows that teams add
   findings that hold.

*Counting the team as one voter (decide).* The project owner's view: the
three act as one and compete for the truth inside the team; that is a
strength, and the statistics should model it rather than rule it out. That
is possible:
- **The team as a voter of its own,** with sensitivity s_T and specificity
  c_T. An error can be shown, so the simplest model is "truth wins": the
  team finds the error if one member does, s_T = 1 − Π(1 − s_i), reduced by
  the share q of findings talked away in the room; c_T at least the median
  of the c_i, since discussion removes false alarms. Teams are drawn anew
  each time, so the parameters of the model are estimated (q, and how far
  c_T exceeds the members'), not the history of a team. Every joint verdict
  on a planted copy is evidence for them.
- **In the decision rule** the team is one vote with the likelihood ratio
  from (s_T, c_T); k_min counts independent voices, and a team is one.
  Whether two strong team voices may stand where three solo voices stand
  follows from the measured s_T and c_T through the posterior (§6), not
  from a setting.
- **Without a team model:** the members' own verdicts count with a
  correlation discount, n_eff = n / (1 + (n − 1)ρ), with ρ the measured
  correlation of verdicts within teams (the simulation already models ρ
  for correlated blind spots, `--blind-share`).
- **Competition pays:** a confirmed finding is credited, as recognition
  (C-38), to the member who raised it first, in the own verdict or in the
  room (recorded per post), so that disagreeing with the team pays when one
  is right.

*Planted members (project owner, 2026-11-19).* A share of teams gets a PVV
or maintainer as a planted member who knows the answer and argues for the
wrong side on purpose: on a planted copy that it is fine, on a training
ticket with a known correct answer (C-48) that it has an error. Planted
errors measure whether someone finds an error; a planted member measures
whether someone holds a correct finding under pressure and whether they
follow a wrong one, so q directly, per person and overall. Conditions:
- **Only where the answer is known** (planted copies, training tickets).
  The planted member's verdicts and findings count for nothing and open no
  claim; on a team with a planted member, the joint verdict counts for
  nothing either. The other members' own verdicts count as always.
- **Announced, like planted errors** (Kerckhoffs): the rules say that a
  share of teams has a planted member, not which. Revealed to the team with
  the reveal of the planted errors, with the planted member's explanation.
- **Indistinguishable.** No role badges in team rooms (a maintainer badge
  would give the planted member away and invite deference instead of
  argument); guidelines for planted members on what to argue and at what
  pace; arguments on the content only.
- **Kept apart.** The planted member knows which version is the copy and is
  excluded from the declaration's other tickets (C-39).
- **Use.** A member's q enters the team model above and their feedback, not
  the trust of solo reviews, where it plays no part.
- **Cost and limits.** PVVs and maintainers are scarce; a small share,
  first in onboarding teams, where the planted member explains afterwards.
  It is a different quality from a planted error: a person who argues
  against their knowledge in a conversation. Announcement and reveal keep it
  fair; the pilot measures who leaves after such a reveal.

Recommended order: own verdicts first (point 2) cost nothing statistically
and give the data: on every planted copy a team met, the own verdicts and
the joint verdict side by side. They estimate q, c_T and ρ. If the joint
verdict beats the union of the own verdicts, the team vote replaces the own
verdicts in the decision, and point 4 ("never remove") can be relaxed by
the measured q. Before the pilot the harness gets a team agent (truth wins,
steering with probability q) to show from which values teams pay off.

*Cost:* the three members are the seats a ticket has anyway; new are the
waiting time until a team forms and the moderation of team rooms. Counted
as one voter (above), a team fills one of the k_min seats.

*Events:* `team.formed` (ticket, members as reviewer ids, in the vault
whether they are linked), `team.verdict`, posts of the team room like posts
of threads, but not public.

*Pilot measures:* findings added by teams and how many were confirmed; how
often a member with an own finding disagreed with the joint verdict (the
steering effect); joint against own verdicts on planted errors; time to a
decision and returns, with and without teams.

*Order:* after C-48 (onboarding); for courses after C-43. *Status:*
proposal; nothing built.

### C-51 · §8.8, OS-3, SR-24, C-17, C-31, C-42 — Passages located by a model, confirmed by a vote · new
*Request (project owner, 2026-11-19):* paper passages are linked to the
tickets with the help of a language model; where that fails, it is shown. In
a separate strand a community, mostly maintainers and possibly lay judges,
votes on whether the linked passage belongs to the declaration.

*Today:* a PVV or maintainer of the domain proposes a passage, another
maintainer confirms it (C-42, step 2), before the first review. The
passages of the walkthrough's openai/math papers were written by an
assistant as paraphrases, marked "to be confirmed by a maintainer". Mapping
by hand is the bottleneck of breadth first (C-28).

*Proposed:*
1. **The model locates, it does not write.** The passage is the reference the
   review compares with. A model that has seen the Lean statement and
   rephrases the passage moves it towards the Lean; then the reference
   confirms what it should check. The model therefore returns a location
   only (source file, section, lines of the TeX source; page and region for
   papers without source) and the kind of place (numbered theorem,
   definition, prose). The text is cut from the source mechanically by that
   location; a proposal whose text does not occur verbatim in the source is
   void. The TeX source is preferred (arXiv), so formulas stay formulas.
2. **The main theorem from the paper's side.** Its passage is located from
   the claims of the paper (abstract, introduction, numbered theorems;
   C-31), not by similarity to the Lean statement; otherwise the model picks
   the place that fits a flawed statement best, for instance a weaker
   corollary.
3. **Which model.** Never one of the provider whose models produced the
   reviewed proof (C-17); for openai/math no OpenAI model. Model, version,
   prompt and hashes of the inputs go into `passage.proposed` (by:
   machine), so every machine proposal can be told apart and repeated.
4. **"Not found" is information.** Shown on the ticket and per submission
   on the progress page, with the model's category: auxiliary lemma (normal,
   most have no place in the paper), not in the paper, unsure. A main
   theorem without passage is not opened (as today). A claim of the paper
   without a Lean counterpart is a finding for C-31.
5. **The vote asks one narrow question:** "Is this the place where the paper
   makes this claim or gives this definition?" Answers: yes; another place
   (with location); not in the paper. It does not ask whether the passage
   matches the Lean: that is the review itself, and a vote on it beforehand
   would anchor the reviewers.
6. **Who votes.** Maintainers and PVVs of the domain, as today. Lay judges
   (any signed-in account) may join and earn weight the way reviewers do:
   their tasks contain planted wrong mappings (the neighbouring theorem, a
   weaker version, the definition of a similar object) that they must
   reject. Authors of the submission do not vote (C-45, point 5). The
   minimum stays four eyes: the machine proposes, a maintainer of the domain
   confirms; other votes are evidence, and a weighted objection sends the
   passage to a second maintainer.
7. **Closed before the first review.** The reference must not change while
   verdicts are given (C-42, "why reviewers do not vote on passages").
   Afterwards reviewers contest a passage (SR-24); the contest goes back
   into this strand, and a changed passage needs the submission opened again.
8. **Verbatim, not paraphrased.** The binding passage is a short quote with
   its location and a link to the source, so every reviewer can check it in
   the paper; the paper's licence and the right of quotation apply. A
   paraphrase may be shown in addition, never as the reference.
   Consequence for C-41 (decide): planted errors on the paper side need
   uniform paraphrases and are not possible with verbatim quotes; proposed
   is to drop them for passages.

*Events:* `passage.proposed` with by = machine and the model's details, or
with location none and a category; `passage.voted` (new);
`passage.decided` as today.

*Pilot measures:* share of machine proposals confirmed unchanged; how often
lay judges and maintainers reject planted wrong mappings; contests (SR-24)
for machine-located against hand-mapped passages; time from submission to
opening.

*Order:* after C-42 step 2 (built); the paper source comes with the
submission (C-45). *Status:* proposal; nothing built.

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
submissions. Domain and difficulty must both match; difficulty is an upper
bound. The reviewer is told when the preferences could not be used for a set,
without the reason." See C-22; limits on rerolling in S-29.

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
*Proposed:* "Votes on posts and on threads shall influence neither trust,
roles nor decisions; they only sort. A vote on a thread says whether the
discussion is worth reading, not whether the decision is right. A post can
lead to a change of a decision only through a reopen request decided by a
maintainer." See C-25.

### S-23 · SR-42 Interim reports — a public progress page · refine
*Proposed:* Add to SR-42: "The anytime report of every submission is public
and live: PRL, class-A coverage, decided declarations, confirmed findings,
estimated residual error and forecast. It counts declarations, not tickets,
counts a declaration as decided only when all its tickets are, and shows no
live verdict tallies." See C-26.

### S-24 · New requirement: Mathlib in class-A statements · new
*Proposed:* "Every class-A ticket shall list the library definitions its
statement uses directly, with definition, docstring and known conventions.
Library definitions used by class-A statements shall be reviewed by weighted
sampling, once per library version and definition; a decision is reused across
submissions while the definition is unchanged. Trust earned on library tickets
counts for class A at most capped." See C-27.

### S-25 · New requirement: triage before depth · new
*Proposed:* "Every opened submission shall be triaged before it is reviewed in
full: its main theorem, a weighted sample of its class-A units and a sample of
the library definitions it uses. Full class-A coverage, library definitions and
class B follow by priority (interest, reach, triage findings). Reports state
the stage of every submission and label sampled results as such." Affects
SR-38 (choice sets) and SR-42 (reports). See C-28.

### S-26 · S-13 Kernel replay — the trusted base · refine
*Proposed:* Add to S-13: "The official packages of a pinned version should be
replayed through the kernel once, and the result shared by all submissions on
that version; an independent kernel should re-check replayed modules. Reports
list the trusted assumptions: kernel, library versions and whether they were
replayed, and the library definitions used with their review status." See
C-29.

### S-27 · SR-21 Infoview — conventions that depend on the instance · refine
*Proposed:* Add to SR-21: "For norm, distance, inner product, order, measure
and topology, the ticket shall name the type the instance was resolved on, and
its convention where one is known." See C-30.

### S-28 · New requirement: the claims of the paper and their coverage · new
*Proposed:* "Before class A, the main claims of the paper shall be listed with
their passages, and each mapped to a declaration or marked as not formalized.
Reports state how many claims are formalized and name the missing ones; a
missing claim is a finding." Affects SR-24 (paper mapping) and SR-42
(reports). See C-31.

### S-29 · SR-38, SR-39 Choice sets — limits on rerolling · refine
*Proposed:* Add to SR-38: "Per reviewer and 24 hours, at most N_unused choice
sets may be left unused (expired or discarded without a ticket taken; sets
drawn at the work-in-progress limit excluded), and at most N_sets drawn in
all. Preferences may change at most N_pref times a day. Preferences may raise
how often a paper is offered to a person by at most τ_max over the uniform
draw." Values for the pilot: N_unused = 6, N_sets = 24, N_pref = 3; τ_max from
the simulation. See C-32.

### S-30 · SR-31 Hand-overs — rerouting in the pilot · refine
*Proposed:* Move hand-over type 3 (rerouting to another domain) from M6 to the
pilot; type 2 (partial votes) stays in M6 until the decision rule is extended
per question. See C-33.

### S-31 · SR-41 Identity · refine
*Proposed:* Add: "Identity strength grades the start: university sign-in or
linked profiles start normally; e-mail only starts with more entry planted
errors and less initial weight. Phone numbers, if used to detect duplicate
accounts, are stored only as keyed hashes." See C-34.

### S-32 · OS-2 Onboarding — preferences at sign-up · refine
*Proposed:* Add to OS-2: "At sign-up, a person may state preferred domains;
the form states that a preference is not a qualification. Entry tickets come
from the preferred domains where possible." See C-32.

### S-33 · §12.8 Data — preferences and choice data · decide
*Proposed:* Decide whether preferences, choice sets and choices stay in the
public audit log, move to the vault, or are published as commitments only.
See C-35.

### S-34 · SE §8.3 Mixed form — context for class A · refine
*Proposed:* The assumption "a class-A declaration can be judged without much
context" fails for declarations whose content lies in another one (Erdős 970:
the main theorem states only a name). Add: "Class-A tickets unfold the
declarations of the submission they build on, on request; every person sees
every declaration in one version." See C-39.

### S-35 · SR-21 Infoview — content and definitions on request · refine
*Proposed:* Add to SR-21: "The glossary shows, for constants of the
submission, their content (unfoldable), and for Lean and Mathlib constants
their definition on request. Hover works for every link of a dotted name."
Complements S-14 and S-27. See C-39.

### S-38 · SR-35, SR-13, SR-24, new requirement — Roles · new
*Proposed:* Replace the single maintainer role by: reviewer, PV and PVV,
earned per domain by measured trust; maintainer, appointed per domain by an
administrator, only if PVV there (or as founding maintainer with an end date);
administrator for the platform. Add: "Voting weight comes only from measured
trust. Administrators review nothing. A maintainer who saw the original of a
declaration under review does not review it. Passages and domain corrections
need a proposal and a confirmation by two different people; escalations are
decided by a panel of three maintainers of the domain." See C-42.

### S-36 · new requirement — Courses · new
*Proposed:* A requirement for courses: a course lead role scoped to one course
(strong identity, confirmed by a maintainer, no view of tickets under review);
at most one member of a course per ticket; a pool of submissions or domains
inside which students draw as everyone does; membership and the link to the
student in the vault, with consent; no grades from the platform. See C-43.

### S-37 · SR-42 and the discussions — finding problems: hashtags and filters · new
*Proposed:* Add: "Maintainers give a submission hashtags that name the
problem, its family and its subject (event `submission.tagged`). The
progress page and the discussions can be filtered by hashtag, domain,
paper or source, and status or outcome. Hashtags never enter the draw and
exist only per submission. What a person filters for is not recorded."
See C-44.
