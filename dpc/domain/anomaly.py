"""Anomaly signals against gaming (FMEA R1, docs/adr/0006).

A reviewer who recognises honeypots by comparing with the public repository
has an excellent honeypot record but misses real errors. The signal compares
the lower confidence bound of the honeypot detection rate with the upper bound
of the detection rate on *confirmed real* errors. It needs some confirmed real
errors per reviewer, so it is slow — one of several signals, not a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from dpc.domain.sampling import clopper_pearson


@dataclass(frozen=True)
class DetectionRecord:
    honeypots_seen: int = 0
    honeypots_found: int = 0
    real_errors_seen: int = 0  # items later confirmed erroneous
    real_errors_found: int = 0


def honeypot_gap(record: DetectionRecord, alpha: float = 0.05) -> float:
    """``LB(honeypot rate) − UB(real-error rate)``; > 0 means the two rates are
    significantly different, i.e. honeypots are found by other means."""
    if record.honeypots_seen == 0 or record.real_errors_seen == 0:
        return 0.0
    hp_low, _ = clopper_pearson(record.honeypots_found, record.honeypots_seen, alpha)
    _, real_high = clopper_pearson(record.real_errors_found, record.real_errors_seen, alpha)
    return hp_low - real_high


def suspicious(record: DetectionRecord, margin: float = 0.0, alpha: float = 0.05) -> bool:
    return honeypot_gap(record, alpha) > margin
