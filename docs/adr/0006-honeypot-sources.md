# ADR 0006 — Honeypot sources

Status: accepted (2026-11-08) · to be implemented in M2

## Context

Honeypots (concept §5.1) are tickets with a planted, known error. They are the
only place where an error is guaranteed, so they anchor the sensitivity *s* of
every reviewer; without them a reviewer who always answers "correct" looks
perfect, because almost all real declarations are correct.

Two conditions must hold: honeypots must be indistinguishable from real tickets
(SR-06), and the planted error must really be an error (equivalence filter,
SR-07).

The specification already lists the countermeasures against recognisable
honeypots: mutants in the style of the source, mutants from foreign
repositories, anomaly detection ("perfect honeypot rate with low PVV
agreement", FMEA R1), delayed and batched resolution (SR-37). It treats the
camouflage as assumption **AS-5**, to be validated in the pilot (M4).

**Concern.** For a *public* repository at a fixed commit, every mutant can be
compared with its original in about a minute. The comparison also reveals which
tickets are real; answering "correct" on all real tickets and flagging all
differences yields high *s* and *c* without any review work. Mutants from
foreign repositories help only if those repositories are not public. The claim
in concept §15 that the comparison costs about as much as a real review is
therefore doubtful, and a failure of AS-5 is hard to observe in a pilot (those
who game it do not reveal themselves).

## Decision

1. M2 implements the specification as written: Lean-level mutation operators
   (§5.1), type check, equivalence filter, plus anomaly detection and delayed
   batched resolution in M3/M4.
2. The **source of honeypots is pluggable**: mutants of the campaign's own
   repository, of foreign repositories, of a private pool of non-public
   formalizations. Further sources can be added without touching the rest.
3. The concern is recorded as a risk on AS-5. Two possible extensions of the
   specification are kept open, to be decided by the specification owner after
   M2/M4:
   - **Pre-publication review (embargo):** real and honeypot tickets come from a
     repository that is not public during the review.
   - **Informal-side honeypots:** a genuine Lean declaration paired with a
     subtly altered informal statement. Repository lookup reveals nothing;
     detecting the alteration requires the mathematical comparison that the
     review is about. Covers fidelity errors only, and needs independent
     paraphrases for all tickets (SR-24).

## Consequences

- Sensitivity estimates of reviewers may be inflated by gaming until AS-5 is
  validated; the simulation (M3) includes a "lookup" attacker to quantify how
  much.
- Confirmed real errors and machine-checked refutations (weight 1, concept
  §6.2) remain the unforgeable anchors.
