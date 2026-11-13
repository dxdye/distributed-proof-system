# ADR 0011 — Two renderings: with and without the submission's display rules

Status: accepted (2026-11-13) · implemented in `lean/analyzer/RenderMain.lean`
(`dpc-render`), `lean/analyzer/DpcAnalyzer/{Render,ExprJson,Trust}.lean`,
`dpc/lean/render.py`, `dpc/honeypots/mixing.py`, `web/src/components/Infoview.tsx`

## Context

Reviewers judge what the ticket shows them. `dpc-mutate --render` renders the
components of a declaration with the submission's environment extensions
loaded. Those include its own display rules: notation, coercions (`@[coe]`),
unexpanders and delaborators. A submission could therefore print `a ≤ b` as
`a < b`, or hide a function behind `↑`, and reviewers would judge a statement
that is not the one proven. This was the open point of ADR 0009.

Two options were considered:
- render without the submission's rules only, which is honest but loses
  readable notation;
- render both ways and mark differences, which is readable and honest.

The project owner chose the second (2026-11-13).

## Decision

**Every component is rendered twice.**
- `text`: as before, by `dpc-mutate --render` with all extensions.
- `trusted_text`: by `dpc-render`, with the extensions of the toolchain and the
  official packages only.

**`dpc-render` runs no code of the submission.**
1. It walks the import graph and classifies modules by where they are loaded
   from (`DpcAnalyzer.Trust`, as in ADR 0009). Untrusted modules are only read
   as data.
2. Only then does it allow initializers and import the trusted modules the
   untrusted ones depend on, with their extensions (Lean, Mathlib).
3. Every untrusted constant a component mentions is added as an axiom with its
   type. Rendering needs no more, and the kernel replay has checked the
   declarations.

A separate process is required. Filtering the submission's extension entries
in the process that loaded them would not be enough: its initializers have
already run and can change global pretty-printer tables.

**Same settings.** Both programs use the same `pp` (binder types shown) and the
same glossary code (`DpcAnalyzer.Render`). On a project without display rules
of its own, both renderings agree on every component and every mutant
(`tests/test_display.py`).

**Honeypots get both renderings, or none.**
- The mutated expression travels from `dpc-mutate` to `dpc-render` as JSON
  (`DpcAnalyzer.ExprJson`). The encoding is exact: binder names and kinds,
  `mdata`, levels.
- `dpc-mutate` checks that decoding gives back the same expression.
  Otherwise, or above 1 MB, the mutant gets no encoding.
- `honeypot_view` refuses a mutant without a plain rendering whenever the real
  view has one. Otherwise the honeypot would stand out.

**Client.**
- If any component differs, the ticket shows a warning. The plain rendering
  comes first ("Plain: Lean and Mathlib notation only"); the submission's
  rendering follows ("As the submission displays it").
- Hover types and the glossary always come from the plain rendering.
- If nothing differs, a short note says so.

**Pipeline.** `dpc render` and `dpc mutate` run `dpc-render` after
`dpc-mutate` and merge the result into `views.jsonl` and `mutants.jsonl`. The
demo does the same.

## Consequences

- A display rule can no longer change what is judged. Where it changes the
  picture, reviewers see both versions and are told which one counts.
- The display fixture (`lean/fixtures/display`) prints every `≤` as `<`. The
  plain rendering exposes it:
  `∀ (n : Nat), 0 < n → n < n + 1` versus `∀ (n : Nat), 0 ≤ n → n ≤ n + 1`.
  Honest declarations of the same file, including field notation on its own
  structure, look the same both ways.
- Measured on the case studies (2026-11-13):
  - quasi-Riemann: 1 component, Navier–Stokes: 15 components. **No
    differences.**
  - All usable mutants (7 and 47) got their second rendering.
  - Run time: each run (`dpc render`, `dpc mutate`) took under a minute.
- Some differences could still be harmless, for example structure-instance
  notation for the submission's own structures, whose structure information
  lives in an extension. They are shown like any other difference. The reviewer
  sees both versions, so nothing is hidden.
- One more import of the trusted base per render run. No foreign code runs in
  it.

## Not covered

- **Misleading names.** `def Real := Nat` displays honestly as `Real`.
  Whether the name fits the definition is part of the class-A review:
  definitions are in TCB_new, and their bodies are shown.
