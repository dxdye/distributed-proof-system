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
  ("`M ↔ D`" → "the changed part is equivalent in its local context").
- Further filters may follow, e.g. discarding mutants that an automatic lint
  already detects (they would measure the linter, not the reviewer).
