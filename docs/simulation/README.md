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

## Not yet modelled

Lenses and Delphi rounds (correlated blind spots are modelled, lenses are
not), the IRT model with item difficulty, leases and aborts, Sybil accounts and
collusion between PV and PVV.
