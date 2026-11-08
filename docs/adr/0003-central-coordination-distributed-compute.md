# ADR 0003 — Central coordination, distributed computation

Status: accepted as direction (2026-11-08) · partly implemented

## Context

Distributed Proof Check is distributed in two senses: many volunteers work on
tickets, and Lean work (builds, analyses, evidence checks, mutation filters) is
heavy. Distributing *state* would require consensus; distributing *computation*
does not, if the computation is deterministic.

Expected load is small: SR-22 asks for 2000 reviews per week, i.e. roughly one
write every five minutes.

## Decision

1. **One sequencer.** The hash chain (ADR 0002) is a total order with a single
   writer. Concurrent writers are serialised by an immediate transaction on the
   log head. No distributed consensus anywhere.
2. **Lean jobs are pure functions of content hashes.** A built environment is
   addressed by `artifact_key = SHA-256(toolchain, manifest, commit)`; job
   results by the hash of their inputs. Jobs are idempotent, may be retried and
   cached, and workers may crash. Workers scale horizontally.
3. **One lease primitive for people and machines.** Tickets lent to reviewers
   (concept §9.1) and jobs handed to workers use the same mechanism: expiry,
   one renewal, return to the pool (as in BOINC). Only the server's clock
   decides.
4. **Job queue in PostgreSQL** (`SELECT … FOR UPDATE SKIP LOCKED`) instead of an
   extra message broker — one component less, transactional with the log.
5. **No volunteer computing for Lean jobs.** Build outputs from untrusted
   machines cannot be trusted, and the checks are cheap enough to run centrally.

## Consequences

- Implemented so far: `artifact_key`, the `LeanExecutor` interface with host and
  sandbox implementations, the single-writer audit log.
- Open (M4): job queue, leases, worker pool, artifact store for built
  environments (Mathlib alone is several GB and is shared between all
  repositories pinned to the same Mathlib version).
