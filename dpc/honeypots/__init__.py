"""Honeypots: mutants with a known error, mixed into the ticket stream (M2).

Concept §5.1, SR-06, SR-07, docs/adr/0006 (sources) and docs/adr/0007 (local
equivalence filter).
"""

from dpc.honeypots.mixing import MAX_SHARE, Slot, TicketView, plan_stream
from dpc.honeypots.model import SCHEMA, Mutant, MutantSet
from dpc.honeypots.sources import (
    HoneypotPool,
    HoneypotSource,
    MutantFileSource,
    Origin,
    SourceSpec,
    load_registry,
)

__all__ = [
    "MAX_SHARE",
    "SCHEMA",
    "HoneypotPool",
    "HoneypotSource",
    "Mutant",
    "MutantFileSource",
    "MutantSet",
    "Origin",
    "Slot",
    "SourceSpec",
    "TicketView",
    "load_registry",
    "plan_stream",
]
