# Simulation results (M3)

The agent-based simulation (`dpc/sim`) runs the production domain core
(`dpc/domain`) against a known ground truth. The table in
[parameter-study.md](parameter-study.md) is generated with
`pixi run dpc study`; increase `--seeds` before drawing firm conclusions — with
300 items and an error rate of 5 % a run contains only about 15 erroneous
items, so a single miss moves the miss rate by about 0.06.

## Findings (2026-11-08, 2 seeds)

1. **Without attackers the decision rule holds.** The miss rate is 0 in almost
   all configurations at about 3–3.6 reviews per item; "always correct"
   clickers never qualify as PV and never review class A.
2. **Honeypot lookup attackers are the dominant risk.** With about 9 % of
   reviewers gaming honeypots via the public repository (docs/adr/0006), the
   miss rate rises to up to 15 % with `k_min = 2`. They take 10–29 % of all
   class-A reviews because they earn *more* trust than honest reviewers.
3. **`k_min = 3` is the robustness margin.** It brings the miss rate under
   attack down to 0–6 %. Recommendation for OD-5: `k_min = 3`.
4. **A high θ_PV does not keep attackers out.** At θ_PV = 0.6 fewer than 10 %
   of honest reviewers qualify, while attackers still do. θ_PV ≈ 0.3–0.45 keeps
   35–75 % of honest reviewers in the pool; calibrate in the pilot.
5. **A higher honeypot share h does not help against lookup.** It costs
   volunteer time (honeypots per item 1.3 → 1.9) and hands attackers more free
   credit. h = 0.05–0.1 is sufficient; the default 0.1 of SR-06 is fine.
6. The anomaly signal flags 12–62 % of attackers within one campaign; it needs
   confirmed real errors and is therefore slow (FMEA R1).

**Consequence.** Tuning h and θ_PV cannot compensate for recognisable
honeypots. What matters is honeypot camouflage (ADR 0006: embargo, private
pools, possibly informal-side honeypots) and the unforgeable anchors
(machine-checked refutations, confirmed real errors).

## Extended model (2026-11-08, 3 seeds × 400 items, error rate 0.1)

| Mechanism | Result |
|---|---|
| **Lenses** (concept §8.3–8.4), ρ = 0.5 | identical reviews miss **100 %** of blind errors (overall miss rate 52 %); with greedily chosen lenses **33 %** (overall 15 %) |
| **IRT** (concept §8.2), honeypots 2.5 units easier than real errors | κ of honest reviewers rises from 0.42 to 0.55, miss rate from 4.9 % to 8.0 % — honeypots must span the difficulty range |
| **Delphi** (concept §8.6) | switching to a *wrong* justification: honest 7 %, easily led reviewers 58 % — a clean signal of influenceability; switching to a *right* one: 50 % vs 88 % |
| **Sybil** (FMEA R6), target items | 5 Sybil accounts among 40 honest: 0 % of targets pass (random assignment + one-finding rule); 40 against 10: **71 %** pass — protection rests on one account per person (SR-41) |
| **Collusion PV ↔ PVV** + pair window (SR-08) | repeated (PV, PVV) pairs 579 → 41 with a window of 50 checks; target success 12.5 % → 8.8 % |

Consequences: lenses are the effective countermeasure against correlated blind
spots (repetition is not); honeypot difficulty must be matched to real errors;
the Sybil defence is identity, not statistics; the pair window works.

Reproduce, e.g.: `pixi run dpc simulate --items 400 --error-rate 0.1 --blind-share 0.5 --lenses --runs 3`
(switches: `--irt --honeypot-shift`, `--delphi`, `--sybils/--colluders --target-share`,
`--pair-window`). Tests: `tests/test_simulation.py` (marked `slow`).

## Steering by choosing and rerolling (C-32, 2026-11-15)

Full table: [`steering.md`](steering.md), from `pixi run dpc steering-study`
(600 items, error rate 0.1, 40 honest reviewers, one attacker whose accounts
gain trust by looking up planted errors and pass the attacker's targets, half
of the erroneous items; 5 seeds pooled).

How much more often an attacking account reaches a target than an honest one
(τ) follows from the coordinator's limits: τ = N·(1 − (1 − n/N)^m) for N open
tickets, sets of n and m sets seen per ticket taken
(`dpc.sim.study.steering_factor`). Choosing alone gives τ = n = 4: an attacker
takes its target whenever a set shows it. With 24 sets a day and one ticket
taken (before C-32) τ ≈ 79 for N = 200; with at most 6 unused sets a day,
τ ≈ 26 for one ticket a day and ≈ 8 if every ticket taken costs one unused set.

| accounts | τ = 1 | τ = 4 | τ = 8 | τ = 26 | τ = 79 |
|---|---|---|---|---|---|
| 5, full weight | 4 % | 8 % | 13 % | 22 % | 45 % |
| 10, full weight | 9 % | 30 % | 55 % | 82 % | 94 % |
| 10, identity weight 0.5 | 3 % | 1 % | 5 % | 4 % | 3 % |

Share of target errors accepted; the other erroneous items are missed in about
1 % of cases. Identity weight 0.5: the attacking accounts' estimated rates are
shrunk halfway towards 0.5 in the decision rule; it costs 0.2–0.8 more reviews
per item (3.4–3.7 → 3.8–4.3).

Consequences:
- Limits on rerolling lower τ but cannot bring it near 1, since choosing is
  itself a lever. They are worth having (79 → 26), not sufficient.
- What stops the attack is the weight of the accounts: they earn it here by
  looking planted errors up (C-07), and lose most of it with a graded start by
  identity (C-34). Both levers, private planted errors and identity, matter
  more than any parameter of the draw.
- A bound τ_max on preferences of 2–3 is small next to the τ of choosing and
  rerolling; it keeps preferences from adding to it.
- The model shrinks only the attackers' weight. If every weakly identified
  account, honest or not, starts with less weight, the cost in reviews is
  higher; to be measured in the pilot.

## Not yet modelled

Leases and aborts, paired review, payouts. Choice sets are modelled only through
the steering factor τ, not as sets of tickets with attention ψ.
