"""Parameters of the coordination service (concept §6–§10; SR-11, SR-26–SR-30, SR-37).

Defaults follow the concept and the M3 parameter study
(docs/simulation/parameter-study.md). They are logged when the service starts
(event ``coord.configured``), so every decision can be traced to the parameters
in force.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from dpc.domain.decision import DecisionParams
from dpc.domain.trust import DEFAULT_WEIGHTS, RoleThresholds, Source

DAY = 86_400


@dataclass(frozen=True)
class CoordParams:
    decision: DecisionParams = field(default_factory=DecisionParams)
    roles: RoleThresholds = field(default_factory=lambda: RoleThresholds(0.45, 0.7))
    #: SR-28: class-A tickets are issued in parallel to k_min + extra_parallel persons.
    extra_parallel: int = 1
    #: Further review slots per additional round (concept §6.4: more reviews).
    slots_per_extra_round: int = 1
    # --- choice sets (SR-38, SR-39) ---
    choice_set_size: int = 4  # n_S
    choice_set_ttl_s: int = 3600
    #: Hard cap on choice sets per reviewer and day, used or not (C-32).
    max_choice_sets_per_day: int = 24
    #: Sets left unused per day: drawn, then expired or discarded without a
    #: ticket taken from them. Bounds rerolling, the way to see a target ticket
    #: more often than chance allows; taking tickets is not limited by it.
    #: Sets drawn at the work-in-progress limit do not count (C-32).
    max_unused_sets_per_day: int = 6
    # --- leases (SR-26, SR-27, SR-30) ---
    lease_alpha: float = 0.1  # τ = F⁻¹(1 − α)
    lease_min_samples: int = 20  # below this, the default duration applies
    default_lease_s: int = 3 * DAY
    default_expected_s: int = 45 * 60  # shown until enough tickets are finished (SR-30)
    # --- exclusion (SR-08) ---
    pair_window_s: int = 7 * DAY  # Δ_pair
    # --- processing time (SR-29) ---
    t_min_s: float = 300.0  # plausible minimum for a ticket of difficulty 0
    # --- PVV re-checks (SR-13) ---
    rho_min: float = 0.05
    rho_max: float = 0.5
    # --- trust (SR-12) ---
    decay_per_day: float = 0.998  # λ; half-life of evidence ≈ 1 year
    weights: dict[str, float] = field(
        default_factory=lambda: {s.value: w for s, w in DEFAULT_WEIGHTS.items()})
    # --- honeypots (SR-06, SR-37) ---
    honeypot_share: float = 0.1
    reveal_delay_s: int = 7 * DAY
    reveal_batch: int = 5
    # --- evidence (SR-09, SR-10) ---
    max_evidence_bytes: int = 64_000
    #: Shortest justification of an "incorrect" verdict, in characters (SR-09).
    min_reason_chars: int = 30
    # --- difficulty tiers (dpc.coord.tiers) ---
    #: Hard and excellence tickets only for those qualified (trust, group, maintainer).
    tier_gating: bool = True
    #: After this age a ticket is open to everyone, so that none starves (SR-05).
    tier_gate_age_s: int = 14 * DAY
    # --- preferences (SR-32, SR-38) ---
    #: At most this share of a choice set is filled by preference; the rest is random.
    pref_share: float = 0.5
    #: Preferences apply only if the matching tickets come from at least this many
    #: submissions, so that nobody can steer towards one paper (SR-38).
    pref_min_papers: int = 2
    #: A change of preferences discards the current set, so each change is a
    #: reroll; at most this many changes per day (C-32).
    max_preference_changes_per_day: int = 3

    @property
    def parallel(self) -> int:
        return self.decision.k_min + self.extra_parallel

    def source_weights(self) -> dict[Source, float]:
        return {Source(k): v for k, v in self.weights.items()}

    def t_min(self, difficulty: float) -> float:
        """``t_min(i)``: harder tickets need longer (concept §9.3)."""
        return float(self.t_min_s * 2.0 ** max(-2.0, min(2.0, difficulty)))

    @classmethod
    def from_overrides(cls, overrides: dict[str, Any]) -> CoordParams:
        """Defaults with some fields replaced (e.g. from a JSON file);
        ``decision`` and ``roles`` take dictionaries of their own fields."""
        base = cls()
        data = dict(overrides)
        if "decision" in data:
            data["decision"] = replace(base.decision, **data["decision"])
        if "roles" in data:
            data["roles"] = replace(base.roles, **data["roles"])
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown parameters: {sorted(unknown)}")
        return replace(base, **data)

    def as_log(self) -> dict[str, Any]:
        """Decimal strings instead of floats (canonical JSON, ADR 0002)."""
        def enc(value: Any) -> Any:
            if isinstance(value, float):
                return format(value, ".12g")
            if isinstance(value, dict):
                return {k: enc(v) for k, v in value.items()}
            return value
        return enc(asdict(self))  # type: ignore[no-any-return]
