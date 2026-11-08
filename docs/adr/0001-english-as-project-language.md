# ADR 0001 — English as the project language

Status: accepted (2026-11-08)

## Context

The concept paper and the systems engineering document were written in German
for internal use. The source code is published (source-available,
non-commercial; see README), reports and findings are public (constraint CN-2),
and the main audience — the Lean and Mathlib community, reviewers, labs — works
in English.

## Decision

Everything in the repository is English: code, identifiers, docstrings,
comments, user interface, README, ADRs and the requirement catalogue
(`requirements/sr.yaml`, translated from the SE document). Requirement ids
(SR-xx, SN-x, C-x, …) and section references ("concept §6.4") are kept so that
traceability to the original documents is preserved.

## Consequences

- The German source documents stay outside the repository.
- Formula symbols follow the concept paper (κ, s, c, δ_A, …) and are spelled
  out in English where needed.
