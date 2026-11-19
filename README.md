# Distributed Proof Check

Reference implementation of a trust-based ticket system in which many
volunteers harden large — in particular AI-generated — Lean 4 formalizations.

The Lean kernel guarantees that a proof derives its formal statement from the
axioms used. It does **not** guarantee that the statement means what the paper
claims, that definitions mean what their names suggest, or that unusual axioms
are intended. Distributed Proof Check closes that gap with human judgement and
makes the reliability of that judgement measurable:

- **Class A — trusted computing base (TCB):** every declaration the meaning of
  the main theorem depends on is reviewed completely, by reviewers with proven
  trust in the field.
- **Class B — proof internals:** sampled, with a statistical error bound.
- **Ground truth** comes from honeypots (mutated declarations with known
  errors) and machine-checked refutations, so trust cannot be built by mutual
  agreement alone.
- **Everything is logged** in an append-only, hash-chained audit log from which
  the public report is derived.

**Research prototype.** This repository implements the concept and measures it
on real formalizations. It is not a running service, and no review campaign
with real reviewers has taken place. The specification is still changing:
proposed changes are collected in
[docs/spec-change-proposals.md](docs/spec-change-proposals.md), and several of
them await the project owner's decision. Known open risks, with numbers from
the simulation, are in [docs/simulation/README.md](docs/simulation/README.md).
The largest are planted errors that can be recognised by comparison with the
public repository under review ([ADR 0006](docs/adr/0006-honeypot-sources.md)),
and accounts that are not tied to one person (SR-41).

For a first look, open the click dummy, the web client on simulated data in
your browser: <https://dxdye.github.io/distributed-proof-system/>. Locally, with
nothing installed but Node.js: `cd web && npm ci && npm run dev:demo` (details
below).

## Status

| Milestone | Content | State |
|---|---|---|
| M0 | Scaffold, audit log, requirement traceability | ✅ |
| M1 | Lean analysis: axioms, TCB, ticket units, graph diff, sandboxed build, kernel replay of the submission's own modules | ✅ measured on [Navier–Stokes](docs/case-studies/navier-stokes.md) (8 class-A units) and [ζ(s) ≠ 0 for Re s > 7/8](docs/case-studies/quasi-riemann.md) (1 class-A unit) |
| M2 | Mutation generator, local and component equivalence filter, auto-detection filter, honeypot source registry and mixing | ✅ 47 + 7 honeypot candidates; maintainer review of pools open |
| M3 | Trust model, decision rule, Dawid–Skene, sampling, lenses, PRL, priority, attention, forecast; agent-based simulation, parameter study | ✅ study incl. lenses, IRT, Delphi, Sybil, collusion ([findings](docs/simulation/README.md)) |
| M4 | Coordination service (choice sets, leases, exclusion rules, claims, PVV, decisions, delayed honeypot reveal), HTTP API, web client with static infoview, discussion after the decision, public progress page, sign-in via Keycloak/OIDC, evidence checker with kernel replay | ✅ MVP ([ADR 0008](docs/adr/0008-coordination-service.md)); evidence checks not yet wired to claims, pilot open |
| M5 | Class B, certificate, signed report | planned; an unsigned report from the audit log exists (`dpc report`, progress page) |

All 60 system requirements live in [`requirements/sr.yaml`](requirements/sr.yaml);
`pixi run trace` shows which ones are verified by which tests.

## Quick start

Requirements: [pixi](https://pixi.sh), [elan](https://github.com/leanprover/elan)
(for the Lean tests), Docker (for the sandbox).

```bash
pixi install
pixi run test-fast        # offline tests, no Lean or Docker needed
pixi run test             # everything; Lean/Docker tests are skipped if unavailable
pixi run check            # lint + type check + tests
pixi run trace            # tests + traceability matrix in build/traceability.md
```

The workflow "CI" (`.github/workflows/ci.yml`) runs lint, type check and the
tests without Lean, Docker and Keycloak, and builds the web client: on every
push to any branch and on pull requests into `master`. Changes to
documentation only start no run; a newer run of the same branch cancels the
older one.

Analyse a trusted local project (here: the fixture with a hand-checked TCB):

```bash
pixi run dpc analyze-local lean/fixtures/basic --root Basic.main_theorem
```

Ingest a foreign repository in the sandbox (submission format: interface I-1):

```bash
cat > submission.json <<'EOF'
{"repo_url": "https://github.com/<org>/<repo>", "commit": "<40-char hash>",
 "root": "<Namespace.mainTheorem>", "root_module": "<Module>", "paper_ref": "arXiv:…"}
EOF
pixi run dpc ingest submission.json --workdir work/run1 --log data/audit.sqlite
pixi run dpc audit-verify data/audit.sqlite
```

Real-world repositories (e.g. with Mathlib) run in a Docker volume, with the
Mathlib cache fetched without executing the submission (ADR 0005):

```bash
pixi run dpc ingest submission.json --executor docker-volume --workdir work/run1 \
    --cpus 7 --memory 24g --timeout-h 6
```

Try the review web service locally (M4) — the mutation fixture becomes a
submission with planted errors; needs elan and Node.js, no Docker:

```bash
pixi run install-web && pixi run build-web
pixi run demo --params config/demo-params.json      # prints a maintainer token
pixi run serve --data data/demo --params config/demo-params.json
# open http://127.0.0.1:8000, register reviewers, sign in as maintainer with the token
```

Sign in through Keycloak instead (ADR 0010; needs Docker). The development
realm has the users `maintainer`, `reviewer1` and `reviewer2`, password = user
name; `maintainer` holds the realm role `dpc-maintainer`:

```bash
pixi run keycloak-up          # http://localhost:8080, admin console: admin / admin
pixi run serve --data data/demo --params config/demo-params.json --auth config/auth-keycloak.json
```

The realm and `deploy/keycloak/compose.yaml` are for development only: fixed
passwords, plain HTTP and a password-grant client for tests. Never import them
into a system that can be reached from outside.

Or run Keycloak and the web service together in Docker (`compose.yaml`). Both
come back by themselves after a reboot, once Docker Desktop runs. The service
state lives in the volume `dpc-state`, seeded once from `data/walkthrough`
(SQLite in WAL mode is not safe on a Windows bind mount); `DPC_SEED_DIR` and
`DPC_PARAMS` choose other data. Stop a Keycloak started with `keycloak-up`
first, both use port 8080.

```bash
pixi run stack-up             # docker compose up -d --build: http://127.0.0.1:8000
pixi run stack-down           # the state volume stays; `docker compose down -v` drops it
```

A click dummy of the web client (simulated backend in the browser, four roles,
no server needed) is built from a snapshot of the current implementation:

```bash
pixi run dpc export-demo          # writes web/demo/snapshot.json (needs `dpc demo` and the case studies)
cd web && npm run build:demo      # static site in web/dist-demo; `npm run dev:demo` to try it
```

The workflow "Click dummy" builds it on GitHub on every push to `master` that
changes `web/` (or by hand) and, with the repository variable
`PUBLISH_CLICK_DUMMY` set to `true` (as here), publishes it on GitHub Pages:
<https://dxdye.github.io/distributed-proof-system/>. Planted
errors in the dummy come only from own fixtures: whatever is public is burnt
for a real review.

Before hosting the web service, fill in `web/public/legal.json` (operator data
for the imprint and the privacy policy; read at runtime, the pages show a draft
banner while placeholders remain) and have the texts reviewed.

For a real submission: ingest it (above), then render the ticket views,
generate honeypot candidates and open it for review:

```bash
pixi run dpc render submission.json --workdir work/run1
pixi run dpc mutate submission.json --workdir work/run1
# paper.yaml: per class-A declaration the passage of the paper (ADR 0012, SR-24)
pixi run dpc open-submission submission.json --workdir work/run1 --title "…" --lab "…"     --paper work/run1/paper.yaml
pixi run serve
```

Simulate the review process (M3), e.g. with "always correct" clickers and
honeypot lookup attackers:

```bash
pixi run dpc simulate --items 300 --clickers 5 --lookup 5 --error-rate 0.1 --runs 3
pixi run dpc study --seeds 5          # parameter study -> docs/simulation/parameter-study.md
```

## Layout

```
dpc/                  Python package
  audit/              canonical JSON, hash-chained audit log (C11)
  analysis/           analyzer output model, TCB/units, axioms, merge, graph diff, domains
  lean/               Lake projects, host and Docker executors (C1, C2, C7)
  ingest/             submission, trusted fetch, ingest pipeline (host and Docker volume)
  honeypots/          mutant model, pluggable honeypot sources, mixing into the ticket stream
  domain/             pure review model: trust, decision rule, Dawid–Skene, sampling,
                      lenses, leases, PRL and priority, attention, forecast, anomalies
  sim/                agent-based simulation of the review process (M3)
  tickets/            ticket and review records, unit views, class-A generation
  coord/              coordination service (M4): events, projection, vault, commands
  api/                HTTP API (FastAPI)
  auth/               sign-in: pluggable identity providers (API tokens, OIDC, Keycloak)
  tools/              pytest traceability plugin
lean/analyzer/        Lean 4 metaprograms: `dpc-analyze` (TCB extraction), `dpc-mutate`
                      (mutants, equivalence filter, ticket views), `dpc-evidence`
                      (kernel replay and check of evidence files, SR-10), `dpc-replay`
                      (kernel replay of all untrusted modules, ADR 0009), `dpc-render`
                      (views without the submission's display rules, ADR 0011)
lean/fixtures/        test projects: `basic` (hand-checked TCB), `mutation` (known
                      equivalent / non-equivalent mutants), `redteam` (sandbox escape
                      attempts), `evidence` (vacuous and honest claims), `replay`
                      (a proof the kernel never saw), `display` (a misleading
                      display rule)
web/                  React/TypeScript client (Vite)
deploy/keycloak/      development Keycloak (Docker Compose, realm with test users)
deploy/dpc/           image of the web service; `compose.yaml` runs it with Keycloak
docs/case-studies/    measurements on real formalizations
sandbox/              Dockerfile and entry script of the sandbox image
requirements/sr.yaml  system requirements SR-01 … SR-60
docs/adr/             architecture decision records
tests/                pytest; `tests/data` holds recorded analyzer output
```

## Design decisions

- [0001](docs/adr/0001-english-as-project-language.md) English as the project language
- [0002](docs/adr/0002-event-sourced-audit-log.md) The audit log is the single source of truth
- [0003](docs/adr/0003-central-coordination-distributed-compute.md) Central coordination, distributed computation
- [0004](docs/adr/0004-tcb-extraction.md) Extracting the trusted computing base
- [0005](docs/adr/0005-sandbox-and-dependency-fetch.md) Sandbox and dependency fetch
- [0006](docs/adr/0006-honeypot-sources.md) Honeypot sources
- [0007](docs/adr/0007-local-equivalence-filter.md) Local equivalence filter for mutants
- [0008](docs/adr/0008-coordination-service.md) Coordination service
- [0009](docs/adr/0009-kernel-replay.md) Kernel replay and trust by location
- [0010](docs/adr/0010-authentication.md) Authentication: pluggable identity providers, Keycloak first
- [0011](docs/adr/0011-plain-rendering.md) Two renderings: with and without the submission's display rules
- [0012](docs/adr/0012-paper-passages.md) The paper side of a ticket

## Conventions

- Python 3.12, type-annotated, `mypy --strict` on `dpc/`, `ruff` for style.
- Tests reference requirements with `@pytest.mark.req("SR-xx")`; tests that need
  Lean or Docker are marked `lean` / `docker`.
- Commit messages: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.

## License

The software is source-available under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md): it may be used, changed and
shared for noncommercial purposes, including personal research and study and
any use by educational institutions and public research organisations.
Commercial use needs a separate license from the copyright holder. The
documentation (everything in `docs/` and the Markdown files) is licensed under
[CC BY-NC 4.0](LICENSE-docs.txt). Copyright 2026 Tilman-Sören Bertram
([tilmanbertram.com](https://www.tilmanbertram.com)).

Contributions require agreeing to a contributor license agreement, so that the
copyright stays with a single holder. The agreement is not written yet; until
it is, outside contributions cannot be accepted.

Reviews and reports produced *by* the system are a separate matter: they are
published under an open license (SR-49).

### Third-party material

- `web/demo/snapshot.json`, the data of the click dummy, contains declarations
  rendered from
  [openai/NavierStokesAndEuler](https://github.com/openai/NavierStokesAndEuler)
  at commit `f9e8bc5` and from [openai/math](https://github.com/openai/math)
  at commit `4eaee87` (20 papers), both licensed by their authors under the
  Apache License 2.0. The informal statements shown as "the paper says" for
  the openai/math papers are paraphrases of the papers, not quotes, and not
  confirmed by their authors. The people, verdicts and discussions around them
  in the click dummy are invented. They are not an assessment of those
  formalizations. If the snapshot is regenerated with further case studies,
  list their sources here.
- The web client bundles the fonts Inter and JetBrains Mono (SIL Open Font
  License 1.1) and KaTeX (MIT) from their npm packages.
