# ADR 0007 — Local equivalence filter for mutants

Status: accepted (2026-11-08) · implemented in `lean/analyzer/DpcAnalyzer/Mutate.lean`

## Context

Concept §5.1 discards a mutant `M` of a declaration `D` if `M ↔ D` can be
proven automatically, so that a reviewer who judges correctly is never
penalised.

For a **proven theorem** this criterion is wrong. `D` is true, hence `M ↔ D`
is provable exactly when `M` is true. The filter would discard every *true*
mutant — including faithful-looking but different claims such as

    ∀ n, 0 < n → 1 ≤ n      (original)
    ∀ n, 1 < n → 1 ≤ n      (mutant: true, but a different, weaker theorem)

which a careful reviewer comparing with the paper should flag, i.e. exactly
the subtle honeypots the system needs.

## Decision

The filter checks equivalence **locally, at the place of the change**, in the
context of all enclosing variables and hypotheses:

| Operator | Proof obligation (closed over the local context) |
|---|---|
| relation (`<` ↔ `≤`, `>` ↔ `≥`) | `a ↔ a'` |
| constant (`k` → `k ± 1`) | `t = t'` |
| interval (`Set.Icc` ↔ `Set.Ioo`, …) | `s = s'` |
| drop hypothesis | the hypothesis follows from the binders before it |
| swap quantifiers (`∀x ∃y` → `∃y ∀x`) | `(∀x ∃y P) ↔ (∃y ∀x P)` |

Each obligation is attempted with a configurable list of tactic scripts
(default: `rfl`, `decide`, `omega`, `simp`, `simp_all`, …) under a heartbeat
budget. A mutant counts as equivalent only with a genuine proof: elaboration's
error recovery is disabled, and proofs containing `sorry`, unassigned
metavariables or logged errors are rejected. (The first implementation fell
into exactly this trap and "proved" `0 < n ↔ 0 ≤ n`.)

Every candidate must type-check (SR-07). All candidates are written out,
including rejected ones, so the filter rates can be measured (verification
§11.2).

## Consequences

- The filter is a semi-decision: a mutant that is equivalent but not provably
  so is kept. The manual sample check of verification §11.2 remains necessary.
- The specification text of concept §5.1 should be updated accordingly
  ("`M ↔ D`" → "the changed part is equivalent in its local context"); see
  docs/spec-change-proposals.md, C-05.

## Additions (2026-11-08)

- **Component level.** For definition bodies and structure fields — which are
  not proven truths — the filter additionally tries `∀ xs, body ↔ body'` (or
  `=`), respectively `field ↔ field'` under the earlier binders. Example:
  `0 < n ∧ 1 ≤ n` → `0 ≤ n ∧ 1 ≤ n` is not equivalent locally but as a whole.
  Output field `equivalent_by`: `local` or `component`.
- **Automatically detectable mutants.** The checks of concept §5.2 — vacuity
  (`False` from the hypotheses or fields) and triviality (the statement falls
  to trivial tactics) — run on the original and on each remaining mutant. A
  mutant flagged where the original is not (`auto_detected`) would measure the
  checker, not the reviewer, and is not usable. The same checks will run as
  lints on real tickets (M4).
- **Visibility.** A mutant whose rendering (with binder types) equals the
  original's is not usable.
