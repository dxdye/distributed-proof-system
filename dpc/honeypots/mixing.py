"""Mixing honeypots into the ticket stream (SR-06).

The share ``h`` is configurable in ``[0, 0.2]`` (default 0.1). What a reviewer
sees — the :class:`TicketView` — is built by the same code for real tickets and
honeypots and has exactly the same fields; whether a ticket is a honeypot is
stored server-side only (:class:`Slot`). Ticket ids are random, so neither
their order nor their range reveals late-inserted honeypots.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from dpc.honeypots.sources import Candidate, HoneypotPool

MAX_SHARE = 0.2
DEFAULT_SHARE = 0.1


@dataclass(frozen=True)
class TicketView:
    """Everything a reviewer sees. Identical shape for real tickets and honeypots."""

    ticket_id: str
    ticket_class: str
    declaration: str
    statement: str
    context: tuple[str, ...]
    questions: tuple[str, ...]


@dataclass(frozen=True)
class Slot:
    """Server-side record behind a view."""

    view: TicketView
    is_honeypot: bool
    honeypot: Candidate | None = None


QUESTIONS_A = ("fidelity", "junk_values", "edge_cases", "vacuity", "quantifiers")


def new_ticket_id(ticket_class: str) -> str:
    return f"{ticket_class}-{secrets.token_hex(6)}"


def plan_stream(
    real: Sequence[tuple[str, str, tuple[str, ...]]],
    pool: HoneypotPool,
    rng: np.random.Generator,
    *,
    share: float = DEFAULT_SHARE,
    ticket_class: str = "A",
    id_factory: Callable[[str], str] = new_ticket_id,
    contexts: Mapping[str, tuple[str, ...]] | None = None,
) -> list[Slot]:
    """Interleave honeypots so that they make up ``share`` of the stream.

    ``real``: ``(declaration, statement, context)`` of the real tickets.
    Honeypots carry the original declaration name and *its* context (from
    ``real`` or ``contexts``), so the visible fields cannot tell them apart."""
    known = {decl: ctx for decl, _, ctx in real} | dict(contexts or {})
    if not 0.0 <= share <= MAX_SHARE:
        raise ValueError(f"honeypot share must be within [0, {MAX_SHARE}] (SR-06)")
    n_honeypots = round(len(real) * share / (1 - share)) if share else 0
    n_honeypots = min(n_honeypots, len(pool))
    slots = [
        Slot(TicketView(id_factory(ticket_class), ticket_class, decl, stmt, ctx, QUESTIONS_A),
             is_honeypot=False)
        for decl, stmt, ctx in real
    ]
    for _ in range(n_honeypots):
        cand = pool.draw()
        view = TicketView(id_factory(ticket_class), ticket_class, cand.mutant.decl,
                          cand.mutant.mutant, known.get(cand.mutant.decl, ()), QUESTIONS_A)
        slots.append(Slot(view, is_honeypot=True, honeypot=cand))
    order = rng.permutation(len(slots))
    return [slots[i] for i in order]
