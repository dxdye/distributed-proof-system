"""Mixing honeypots into the ticket stream (SR-06).

The share ``h`` is configurable in ``[0, 0.2]`` (default 0.1). What a reviewer
sees — a :class:`~dpc.tickets.views.UnitView` — is built from the same
rendering for real tickets and honeypots: a honeypot is the view of its
original unit with exactly one component replaced by the mutant. Whether a
ticket is a honeypot is stored server-side only (:class:`Slot`, and a
commitment in the audit log, see ``dpc.coord``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from dpc.honeypots.model import Mutant
from dpc.honeypots.sources import Candidate, HoneypotPool
from dpc.tickets.views import UnitView

MAX_SHARE = 0.2
DEFAULT_SHARE = 0.1


@dataclass(frozen=True)
class Slot:
    """Server-side record behind a view."""

    view: UnitView
    is_honeypot: bool
    honeypot: Candidate | None = None


class MutantMismatch(ValueError):
    """The mutant does not fit the view (different rendering or component)."""


def honeypot_view(original: UnitView, mutant: Mutant) -> UnitView:
    """The original view with the mutated component replaced.

    Refuses if the mutant's ``original`` text differs from the component in the
    view: then the two were rendered differently, and the honeypot would be
    recognisable by its formatting alone."""
    if mutant.decl != original.declaration:
        raise MutantMismatch(f"mutant of {mutant.decl} for view of {original.declaration}")
    comp = original.component(mutant.target, mutant.component)
    if comp is None:
        raise MutantMismatch(f"{original.declaration} has no component "
                             f"{mutant.target} {mutant.component!r}")
    if comp.text != mutant.original:
        raise MutantMismatch(f"{original.declaration}: rendering differs from the mutant's")
    # Real tickets carry a second rendering without the submission's display
    # rules (docs/adr/0011). A honeypot without one would stand out.
    if comp.trusted_text is not None and mutant.trusted_mutant is None:
        raise MutantMismatch(f"{original.declaration}: the mutant has no plain rendering")
    if comp.latex is not None and mutant.latex_mutant is None:
        raise MutantMismatch(f"{original.declaration}: the mutant has no typeset rendering")
    update: dict[str, object] = {"text": mutant.mutant,
                                 "glossary": mutant.glossary or comp.glossary}
    if comp.trusted_text is not None:
        update["trusted_text"] = mutant.trusted_mutant
        update["trusted_glossary"] = mutant.trusted_glossary or comp.trusted_glossary
    if comp.latex is not None:
        update["latex"] = mutant.latex_mutant
    replaced = comp.model_copy(update=update)
    return original.model_copy(update={"components": tuple(
        replaced if c is comp else c for c in original.components)})


def fits(view: UnitView | None, mutant: Mutant) -> bool:
    if view is None:
        return False
    try:
        honeypot_view(view, mutant)
    except MutantMismatch:
        return False
    return True


def honeypot_count(real: int, share: float) -> int:
    """Honeypots needed so that they make up ``share`` of the whole stream."""
    if not 0.0 <= share <= MAX_SHARE:
        raise ValueError(f"honeypot share must be within [0, {MAX_SHARE}] (SR-06)")
    return round(real * share / (1 - share)) if share else 0


def plan_stream(
    real: Sequence[UnitView],
    pool: HoneypotPool,
    rng: np.random.Generator,
    *,
    share: float = DEFAULT_SHARE,
) -> list[Slot]:
    """Interleave honeypots so that they make up ``share`` of the stream.

    Only mutants of declarations that have a view in ``real`` are used: a
    honeypot carries the original declaration name and context, so nothing
    visible tells it apart. If the pool runs short, fewer honeypots are mixed
    in (the actual share is in the result)."""
    by_decl = {v.declaration: v for v in real}
    slots = [Slot(view, is_honeypot=False) for view in real]
    for _ in range(honeypot_count(len(real), share)):
        try:
            cand = pool.draw(accept=lambda c: fits(by_decl.get(c.mutant.decl), c.mutant))
        except LookupError:
            break
        view = honeypot_view(by_decl[cand.mutant.decl], cand.mutant)
        slots.append(Slot(view, is_honeypot=True, honeypot=cand))
    order = rng.permutation(len(slots))
    return [slots[i] for i in order]
