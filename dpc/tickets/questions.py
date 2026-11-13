"""The checklist of a class-A ticket (concept §5), by kind of declaration.

A theorem is a claim whose proof the kernel has checked; the reviewer checks
that it claims what the paper claims. A definition or a structure claims
nothing and has no proof: it fixes the meaning of a word, and every theorem
that uses it inherits a mistake in it. The reviewer checks that it defines what
the paper defines.

The five question ids are the same for every kind, so that claims and their
evaluation per question do not depend on the kind; only the wording does.
"""

from __future__ import annotations

from typing import Literal

Kind = Literal["theorem", "definition", "structure"]

QUESTION_IDS = ("fidelity", "junk_values", "edge_cases", "vacuity", "quantifiers")

PURPOSE: dict[Kind, str] = {
    "theorem": "This is the statement of a theorem. The Lean kernel has checked its proof; "
               "check that it states what the paper claims.",
    "definition": "This is a definition. Nothing is proven here: it fixes what a word means, "
                  "and every theorem that uses it inherits any mistake. Check that it "
                  "defines what the paper defines.",
    "structure": "This is a structure (a bundle of conditions or data). Nothing is proven "
                 "here: theorems that assume it rely on exactly these conditions. Check that "
                 "they are the conditions of the paper, no more and no fewer.",
}

TEXTS: dict[Kind, dict[str, str]] = {
    "theorem": {
        "fidelity": "Does the formal statement say what the paper claims — no more, no less?",
        "junk_values": "Could junk values (x / 0 = 0, default values, truncated subtraction) "
                       "make the statement weaker than intended?",
        "edge_cases": "Are the edge cases (empty sets, zero, dimension 0 or 1) handled as in "
                      "the paper?",
        "vacuity": "Can all hypotheses be satisfied at the same time, or is the statement "
                   "vacuous?",
        "quantifiers": "Are quantifiers, their order and the types of bound variables right?",
    },
    "definition": {
        "fidelity": "Does it define what the paper defines (and what its name suggests)?",
        "junk_values": "Where the paper's definition does not apply (division by zero, "
                       "outside the domain), does the value Lean assigns change any theorem "
                       "that uses it?",
        "edge_cases": "Is it right at the edges: zero, empty sets, dimension 0 or 1, "
                      "boundary points?",
        "vacuity": "If it is a property: can it hold at all, and does it not hold trivially "
                   "for everything?",
        "quantifiers": "Are the types right (ℕ, ℤ, ℝ, ℂ; which space), and the order of "
                       "quantifiers inside it?",
    },
    "structure": {
        "fidelity": "Are these exactly the conditions (or data) of the paper — none missing, "
                    "none added, none weakened?",
        "junk_values": "Do junk values of the functions involved (x / 0 = 0, derivatives "
                       "where there is no derivative) make a condition weaker than intended?",
        "edge_cases": "Are the edge cases handled as in the paper: t = 0, the boundary, "
                      "dimension, closed or open intervals?",
        "vacuity": "Can all conditions hold together, so that something satisfies the "
                   "structure? Otherwise every theorem assuming it is vacuous.",
        "quantifiers": "Are quantifiers, their order and the types of the fields right?",
    },
}


def kind_of(decl_kind: str) -> Kind:
    """`dpc-analyze` kinds: theorem, def, opaque, inductive, …"""
    if decl_kind == "theorem":
        return "theorem"
    if decl_kind == "inductive":
        return "structure"
    return "definition"


def questions_for(decl_kind: str) -> list[dict[str, str]]:
    texts = TEXTS[kind_of(decl_kind)]
    return [{"id": q, "text": texts[q]} for q in QUESTION_IDS]


def purpose_for(decl_kind: str) -> str:
    return PURPOSE[kind_of(decl_kind)]
