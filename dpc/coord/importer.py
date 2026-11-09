"""From an ingested submission to class-A ticket specs (SR-04, SR-05, SR-21).

Joins the analysis (units of TCB_new, their domain, static difficulty and
neighbours) with the rendered views of ``dpc-mutate --render``.
"""

from __future__ import annotations

import json
from pathlib import Path

from dpc.analysis import Analysis, assign_domains
from dpc.coord.service import TicketSpec
from dpc.tickets import class_a_tickets
from dpc.tickets.views import UnitView

DEFAULT_DOMAIN = "general"


def load_views(path: Path) -> dict[str, dict[str, object]]:
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    if not lines or lines[0].get("schema") != "dpc.mutants/1":
        raise ValueError(f"{path}: not an output of dpc-mutate")
    return {str(r["decl"]): r for r in lines[1:] if r.get("kind") == "view"}


def ticket_specs(analysis: Analysis, commit: str, views: dict[str, dict[str, object]]
                 ) -> list[TicketSpec]:
    """One spec per class-A unit; every unit needs a rendered view."""
    tickets = class_a_tickets(analysis, commit, assign_domains(analysis))
    missing = [t.declaration for t in tickets if t.declaration not in views]
    if missing:
        raise ValueError(f"no rendered view for {len(missing)} units, e.g. {missing[:3]}")
    return [TicketSpec(view=UnitView.from_render(views[t.declaration], context=t.context),
                       domain=t.domain or DEFAULT_DOMAIN, difficulty=t.difficulty_b)
            for t in tickets]
