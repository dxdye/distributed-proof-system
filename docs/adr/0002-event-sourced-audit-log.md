# ADR 0002 — The audit log is the single source of truth

Status: accepted (2026-11-08) · implemented in `dpc/audit`

## Context

SR-17 requires that the report can be reproduced from the audit log *alone*.
SR-19 requires the log to be append-only and hash-chained. If any state existed
outside the log, the report could depend on it.

## Decision

- Event sourcing: every state change is an event in the audit log; database
  tables, trust values, ticket states etc. are projections that can be rebuilt
  from the log at any time.
- Each entry stores `seq`, `ts`, `kind`, `payload`, `prev_hash` and
  `hash = SHA-256(canonical_json({seq, ts, kind, payload, prev}))`.
- Canonical JSON is a strict subset of RFC 8785: sorted keys, no whitespace,
  UTF-8; **no floats** (format differs between languages), integers within
  ±2⁵³, object keys within the BMP, no lone surrogates. Quantities such as
  probabilities are stored as integers (e.g. basis points) or decimal strings.
- Append-only is enforced twice: database triggers reject `UPDATE`/`DELETE`,
  and `verify()` recomputes the chain. Truncating the tail is only detectable
  against a published head hash, so every report carries the head hash (I-5).
- Event kinds are dotted names (`analysis.completed`, `finding.axiom`, …).

## Consequences

- Projections must be pure functions of the event sequence; anything random
  (sampling, assignment) logs its seed or its outcome.
- SQLite now; PostgreSQL later with the same schema and an equivalent
  append-only rule (see ADR 0003 for the single-writer argument).
- Signing of reports (SR-17) is still open and belongs to M5.
