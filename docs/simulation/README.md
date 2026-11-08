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

## Not yet modelled

Leases and aborts, paired review, choice sets with attention, payouts.
