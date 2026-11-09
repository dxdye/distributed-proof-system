# ADR 0008 — Coordination service

Status: accepted (2026-11-09) · implemented in `dpc/coord`, `dpc/tickets/views.py`,
`dpc/honeypots/mixing.py`

## Context

M4 turns the domain rules of M3 (`dpc.domain`) into a running process. Class-A
tickets are leased to people, reviewed in parallel, re-checked by PVVs, decided,
and honeypots are resolved. The rules are given (SR-05, SR-08, SR-09, SR-11,
SR-13, SR-23, SR-26–SR-30, SR-35, SR-37–SR-39, SR-49, SR-50). This ADR records
how they are put together.

## Decision

**Event-sourced on the audit log.** Every state change is an event in the
hash-chained log (ADR 0002). `Coordinator` validates a command against the
projected `State`, appends the event, and only then applies it. Restarting
means replaying the log. Random choices (choice sets, PVV sampling) are made
by the coordinator and recorded, so a replay never needs the random generator.
Derived values that depend on parameters are logged with the event: the time
factor and the reviewer's roles at review time. The parameters themselves are
logged as `coord.configured` whenever they change. One process, one lock: the
single sequencer of ADR 0003.

**Privacy (SR-23).**
- The log contains no pseudonyms. Reviewers appear as random ids (`R-…`).
- Affiliations and the submitting lab appear as keyed hashes (HMAC-SHA-256).
  The exclusion rule of SR-50 is therefore checkable from the log by whoever
  holds the key, and nobody else can read the affiliations.
- Pseudonyms, API tokens (stored as SHA-256 only), the key and unrevealed
  honeypot openings live in a separate `Vault`, which is never published.
- Trust is never published per person; the API offers aggregates only.

**What a reviewer sees.**
- A unit is shown as its components: the type, the body of a definition, the
  constructors of an inductive type. These are exactly the parts `dpc-mutate`
  mutates. Each component is pretty-printed with binder types and comes with a
  glossary of the constants it uses (static infoview, SR-21).
- A honeypot is the view of its original unit with one component replaced.
  `honeypot_view` refuses a mutant whose `original` text differs from the
  view, because different formatting would give the honeypot away.
- Source text is not shown, because a mutant has none.

**Honeypots: commit, then reveal (SR-06, SR-37).**
- Each ticket's opening `{ticket_id, honeypot, salt, mutant_hash, operator, source}`
  stays in the vault. The log only gets its SHA-256 commitment.
- Honeypots are revealed in batches of at least `reveal_batch`, no earlier than
  `reveal_delay` after their decision.
- Closing a submission opens all remaining commitments, real ones included.
  Anyone can then check that the honeypot status was fixed at creation and
  that the share `h` was respected.
- On reveal, the soft evidence collected on the ticket (PVV comparison,
  consensus, claim decisions) is *replaced* by hard honeypot evidence. Trust is
  therefore folded on demand from evidence records instead of being stored.
- Claim tickets raised on honeypots also calibrate the PVVs who decided them.
- A reviewer never gets two tickets of the same unit, and a choice set never
  contains two. Otherwise comparing the two views would expose the honeypot
  for free.

**Process of a class-A ticket.**
1. *Choice set (SR-38, SR-39).* Up to `n_S` eligible tickets: first one per
   paper, then fill. Random order, no popularity shown. The set stays the same
   until it is used or expires, and the number of sets per day is capped, so
   tickets cannot be rerolled at will. Taking a ticket from the set is binding:
   it becomes a lease.
2. *Eligibility (SR-08, SR-27, SR-50).* A person cannot take a ticket if any of
   these holds:
   - they are an author of the submission;
   - they are affiliated with the submitting lab;
   - they are already involved in the ticket;
   - they have already seen the unit;
   - they share a pair with someone on the ticket within `Δ_pair`;
   - their work-in-progress limit from reliability `r_u` is reached.
3. *Lease (SR-26, SR-30).*
   - `τ` is the `(1 − α)` quantile of finished leases of the same duty and
     difficulty bucket. Below `lease_min_samples` finished leases, a default
     applies.
   - A lease can be extended once and returned without penalty. An expired
     lease lowers only the reliability.
   - The client gets the expected duration (the median), not a countdown.
4. *Parallel review (SR-28).* `k_min + 1` slots in round 1.
5. *Verdicts.*
   - "Incorrect" needs a justification and opens a claim ticket (SR-09,
     SR-35). An optional Lean evidence file goes to a content-addressed blob
     store; its hash is logged.
   - "Correct" is sampled for a PVV re-check with probability `ρ_u` (SR-13).
     If a PVV verdict already exists on the ticket, the comparison happens
     immediately: a PVV cannot review the same ticket twice, and waiting would
     deadlock the ticket.
   - Processing time is measured from lease to submission. Reviews faster than
     `t_min(i)` are down-weighted, not refused (SR-29).
6. *Decision (SR-11).* The rule runs once nothing is pending (open claims,
   held leases, requested PVV reviews) and either `k_min` votes are in or all
   slots are used.
   - Acceptance additionally needs a PVV review. If only that is missing, a PVV
     review is requested before `R` rounds can force an escalation.
   - A confirmed claim decides "error" at once and cancels the remaining leases
     without penalty.
   - If the result is inconclusive, a new round with one more slot opens. After
     `R` rounds the ticket goes to maintainers.
7. *PVV duties* are assigned, not chosen: open claims first (they block
   acceptance), then requested PVV reviews. Maintainers count as PVVs, which
   bootstraps a system in which nobody has earned the role yet.

**Durability and throughput (SR-22).** The log runs in WAL mode with
`synchronous=FULL`: one fsync per event. 2000 reviews, including choice sets,
leases and decisions, take about 40 s on a laptop
(`test_two_thousand_reviews_a_week`). The requirement is 2000 per *week*.

## Consequences

- The audit log is published *with the report*, not live. Live, it would show
  honeypot views next to their decisions.
- Newcomers carry no information (ŝ = ĉ = 0.5): their votes do not move the
  posterior. Before anything is accepted, trust must be earned through
  revealed honeypots, PVV comparisons and confirmed findings. This is
  intended, but it means a pilot needs an onboarding phase (concept §6.5).
- `Δ_pair` limits capacity. With `k_min + 1 = 4` reviewers per ticket, a
  ticket uses six pairs. A one-week window then needs on the order of 80
  active reviewers for 2000 reviews per week. The window is a parameter to be
  set with the simulation (M3).

## Open points

- **Evidence check (SR-10): implemented, not yet wired to claims.**
  - *How it works.* `dpc-evidence` checks a Lean evidence file in the sandbox.
    The file is compiled by plain `lean`; then all its declarations are
    replayed through the kernel from an environment containing only its
    imports. The check requires `dpc_evidence`, the standard axioms only, and
    a time limit. For vacuity it also requires exactly the vacuity goal of the
    target. A proof that `lean` accepted under `debug.skipKernelTC` is rejected
    by the replay (`tests/test_evidence.py`). `Coordinator.confirm_by_machine`
    is the hook for confirmed results.
  - *Why it is not wired yet.* A honeypot's statement does not exist in the
    Lean environment, so a check against the declaration of the same name would
    never confirm a claim on a honeypot. Claimants could then recognise
    honeypots by the missing machine confirmation. PVVs would see
    evidence-backed claims mainly on honeypots, because confirmed real claims
    never reach them.
  - *What it needs.* The check must target the shown statement. The mutant
    cannot be regenerated inside the checker: relation swaps synthesise
    instances, which needs the environment extensions, and loading them would
    run the submission's initializers inside the checker. The plan is to compile
    every honeypot statement as a `def` in a separate target module (no
    evidence code involved), check that it elaborates to the mutant
    (`mutant_hash`), and drop candidates that do not round-trip.
  - *Until then.* Claims are decided by PVVs alone.
- **Delphi round 2 (concept §8.6).** Showing justifications and recording
  revisions as non-independent votes.
- **Honeypots from foreign or private sources** need the *unit view* of their
  original (ADR 0006). Mutant files currently carry only the mutated component.
- **Class B (M5)** and reports from the log (SR-17).
