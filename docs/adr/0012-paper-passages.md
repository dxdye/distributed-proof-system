# ADR 0012 — The paper side of a ticket

Status: accepted (2026-11-14) · implemented in `dpc/tickets/paper.py`, `dpc/coord`
(`TicketSpec.paper`, `ticket.mapping_contested`), `dpc/api/app.py`,
`web/src/components/PaperPanel.tsx`, `web/src/components/MathText.tsx`

## Context

A class-A review asks whether the formal statement says what the paper
claims. The tickets showed only the Lean side. Without the informal statement a
reviewer can judge plausibility, not fidelity, which led to two problems:
- Honeypots that are *true but different* theorems became undetectable. In the
  quasi-Riemann case, `8/8 < s.re` and `7/7 < s.re` are such mutants (the
  classical half-plane Re s > 1).
- The specification asks for the paper passage next to the infoview (OS-3:
  "Infoview + Paper-Ausschnitt → Urteil").

SR-24 requires that the mapping from paper to Lean does not come from the model
or system that generated the proof, and that reviewers can mark it as wrong.

The project owner decided (2026-11-14): for the pilot, a maintainer records the
mapping when the submission is opened and reviewers can contest it. Later, a
dedicated mapping ticket before class A will replace the file.

## Decision

- **Paper map per submission** (YAML, `dpc open-submission --paper FILE`,
  default `<workdir>/paper.yaml`):
  - the source: title, arXiv id and version, URL;
  - who mapped it;
  - per class-A declaration: a locator (theorem number, page) and the informal
    statement, with LaTeX between `$` signs;
  - optionally a corrected domain (SR-04);
  - optionally a note.

  A map naming a declaration that has no view is refused.
- **The passage travels with the ticket.** `ticket.created` carries it, so the
  report can show what was compared. A honeypot gets the passage of its
  original. Next to the paper, a true but different mutant becomes a
  detectable error, and the passage does not give the honeypot away.
- **Client.** "The paper says" next to "Lean says". The statement is typeset
  with KaTeX, bundled locally under the MIT licence; `trust` is off, and only
  KaTeX output becomes HTML. Below it: who mapped it, and a button "This passage
  does not belong to this declaration".
  - If a declaration has no passage, the client says so and links the
    submission's paper reference. The reviewer is then asked to name the passage
    they compared with.
- **Contesting (SR-24).** The holder of a lease can contest the mapping once,
  with a reason of at least `min_reason_chars` characters. The event is
  `ticket.mapping_contested`, and maintainers see all contests
  (`/api/admin/contested`).

## Consequences

- Fidelity becomes reviewable, and honeypot detection rates measure what they
  are meant to.
- Mapping costs maintainer time per submission: a few minutes per class-A
  declaration. Navier–Stokes has 8, quasi-Riemann 1.
- A wrong mapping makes every verdict on the ticket questionable. Contests are
  the safeguard. What a confirmed contest does to the verdicts (re-open the
  ticket, discount verdicts) is still to be decided.
- The demo fixtures carry demo papers. The walkthrough map of quasi-Riemann
  (in `work/`, not versioned) is a labelled paraphrase, not a quote.

## Open points

- Correcting a mapping after opening (an event that replaces the passage and
  clears the contests), and the effect of a confirmed contest on the verdicts.
- The mapping ticket that replaces the maintainer file (concept OS-3, SR-24).
