"""What a statement takes from Lean and its libraries (proposal C-27).

The kernel checks a proof, not what the words of its statement mean. A class-A
statement written in Mathlib terms means what Mathlib's definitions mean,
including the values Mathlib fixes where mathematics leaves a function
undefined. So every ticket lists the library definitions its statement uses,
with their docstrings and the conventions to know, and the checklist names
them (question ``junk_values``).

Notation and coercion plumbing is left out of the list: the arithmetic and
order operators, logic, numerals, pairs, uncurrying and inclusions such as
ℕ → ℕ∞. They stay in the full glossary of each component. Their conventions
(x / 0 = 0, truncated subtraction) are part of the checklist question itself.
Constants with a meaning of their own stay in, even when they are written as
notation: ``⊤`` (``Top.top``) is ∞ in ℕ∞ but ω, analytic, as the order of
``ContDiff``.

The list is computed from the view shown, so a planted copy lists what it
uses: it tells nothing about which ticket is the copy.
"""

from __future__ import annotations

from dpc.tickets.notes import note_for
from dpc.tickets.views import Component, GlossaryEntry, UnitView

PLUMBING: frozenset[str] = frozenset({
    # logic and relations
    "Eq", "Ne", "Not", "And", "Or", "Iff", "Exists", "True", "False", "HEq", "ite", "dite",
    "LT.lt", "LE.le", "GT.gt", "GE.ge",
    # arithmetic operators (their junk values are in the checklist question)
    "HAdd.hAdd", "HSub.hSub", "HMul.hMul", "HDiv.hDiv", "HPow.hPow", "HMod.hMod",
    "HSMul.hSMul", "SMul.smul", "Neg.neg", "Inv.inv", "Add.add", "Sub.sub", "Mul.mul",
    "Div.div",
    # numerals
    "OfNat.ofNat", "OfScientific.ofScientific", "Zero.zero", "One.one",
    # pairs and functions
    "Prod", "Prod.mk", "Prod.fst", "Prod.snd", "SProd.sprod", "Function.HasUncurry.uncurry",
    "Function.uncurry", "Function.comp", "id",
    # inclusions and coercions that do not change a value
    "WithTop.some", "Nat.cast", "Int.cast", "Rat.cast", "Complex.ofReal", "Subtype.val",
    "DFunLike.coe", "ContinuousLinearMap.toLinearMap", "RingHom.id",
    # membership and set-builder notation
    "Membership.mem", "setOf",
})

ORIGINS = ("library", "core")


def glossary_of(component: Component) -> tuple[GlossaryEntry, ...]:
    """The plain rendering's glossary where there is one (ADR 0011): the
    submission's notation could make a constant look like another."""
    return component.trusted_glossary if component.trusted_text is not None \
        else component.glossary


def annotate(entry: GlossaryEntry) -> GlossaryEntry:
    """The current note of a constant. Views rendered earlier carry the notes
    of their time; the table in :mod:`dpc.tickets.notes` grows."""
    note = note_for(entry.name)
    return entry if note is None or note == entry.note else entry.model_copy(update={"note": note})


def annotate_view(view: UnitView) -> UnitView:
    """The view with the current notes in every glossary."""
    return view.model_copy(update={"components": tuple(
        c.model_copy(update={
            "glossary": tuple(annotate(g) for g in c.glossary),
            "trusted_glossary": tuple(annotate(g) for g in c.trusted_glossary),
        }) for c in view.components)})


def relies_on(view: UnitView) -> tuple[GlossaryEntry, ...]:
    """The library and core definitions the declaration uses, without
    plumbing. Those with a convention to know come first, then the order of
    the glossary."""
    seen: dict[str, GlossaryEntry] = {}
    for comp in view.components:
        for g in glossary_of(comp):
            if g.origin in ORIGINS and g.name not in PLUMBING and g.name not in seen:
                seen[g.name] = annotate(g)
    entries = list(seen.values())
    return tuple(sorted(entries, key=lambda g: g.note is None))
