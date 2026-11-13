"""What a reviewer sees of a ticket (interface I-3, SR-06, SR-21).

A unit is shown as its *components*: the type, the body of a definition, the
constructors of an inductive type — exactly the parts `dpc-mutate` mutates
(``mutationTargets`` in ``lean/analyzer/MutateMain.lean``). Each component is
the elaborated term pretty-printed with binder types, plus a glossary of the
constants it uses (name and type: the static part of an infoview).

Every component is rendered twice (docs/adr/0011): ``text`` with the
submission's own display rules (notation, coercions, unexpanders), and
``trusted_text`` with those of Lean and the official libraries only. Where the
two differ, the submission's display rules change what a reviewer sees, and
the client shows both.

Real tickets and honeypots are built from the same rendering: a honeypot is the
view of its original unit with exactly one component replaced by the mutant
(`dpc.honeypots.mixing.honeypot_view`). The source text is deliberately not
shown — a mutant has none, so showing it for real tickets would mark every
ticket without it as a honeypot.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Target = Literal["type", "value", "ctor"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GlossaryEntry(_Model):
    name: str
    type: str


class Component(_Model):
    target: Target
    label: str = ""  # the constructor, for target "ctor"
    text: str
    glossary: tuple[GlossaryEntry, ...] = ()
    #: Without the submission's display rules; None if not rendered.
    trusted_text: str | None = None
    trusted_glossary: tuple[GlossaryEntry, ...] = ()
    #: The same term typeset as LaTeX (docs/adr/0012); None: no unambiguous form.
    latex: str | None = None

    @property
    def display_differs(self) -> bool:
        return self.trusted_text is not None and self.trusted_text != self.text


class UnitView(_Model):
    declaration: str
    decl_kind: str
    components: tuple[Component, ...]
    context: tuple[str, ...] = ()  # neighbouring units of TCB_new (go-to-definition)

    @classmethod
    def from_render(cls, record: dict[str, Any], context: tuple[str, ...] = ()) -> UnitView:
        """From a ``"view"`` record of ``dpc-mutate --render``."""
        if record.get("kind") != "view":
            raise ValueError("expected a 'view' record")
        return cls(declaration=record["decl"], decl_kind=record["decl_kind"],
                   components=tuple(Component.model_validate(c) for c in record["components"]),
                   context=context)

    def component(self, target: Target, label: str = "") -> Component | None:
        for comp in self.components:
            if comp.target == target and comp.label == label:
                return comp
        return None
