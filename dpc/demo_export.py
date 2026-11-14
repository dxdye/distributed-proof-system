"""Snapshot for the click dummy (``dpc export-demo``): the web client with a
simulated backend, for an impression of the review in its different roles.

Everything comes from the current implementation: ticket views rendered by
the analyzer (both renderings, LaTeX, glossary), tiers, paper passages, the
checklist questions and the registration notice.

Honeypots come **only from own fixtures**. Whatever is shown publicly is
burnt for a real review (concept C-07: planted errors can be looked up), so
the real case studies appear with their actual statements and no mutants.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dpc.api.app import NOTICE
from dpc.coord.params import CoordParams
from dpc.coord.service import NOTICE_VERSION
from dpc.coord.tiers import tier_of_view
from dpc.honeypots.mixing import MutantMismatch, honeypot_view
from dpc.honeypots.model import MutantSet
from dpc.tickets.paper import PaperMap
from dpc.tickets.questions import PURPOSE, TEXTS
from dpc.tickets.views import UnitView

SCHEMA = "dpc.click-dummy/1"


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    repo_url: str
    commit: str
    domain: str
    views: Path
    paper: Path | None = None
    mutants: Path | None = None  # own fixtures only
    honeypots: int = 0
    paper_ref: str | None = None
    root: str | None = None  # the main theorem


def _views(path: Path) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    return [r for r in lines[1:] if r.get("kind") == "view"]


def _ticket(tid: str, view: UnitView, domain: str, paper: PaperMap | None,
            honeypot: dict[str, str] | None = None) -> dict[str, Any]:
    passage = paper.passage(view.declaration) if paper else None
    return {
        "ticket_id": tid,
        "declaration": view.declaration,
        "decl_kind": view.decl_kind,
        "domain": (paper.domain(view.declaration) if paper else None) or domain,
        "tier": tier_of_view(view),
        "view": view.model_dump(mode="json"),
        "paper": passage.model_dump(mode="json") if passage else None,
        "honeypot": honeypot,  # the mock reveals it right after the verdict
    }


def export(sources: list[Source], out: Path) -> dict[str, int]:
    submissions = []
    counts = {"tickets": 0, "honeypots": 0}
    for n, src in enumerate(sources, start=1):
        paper = PaperMap.load(src.paper) if src.paper and src.paper.is_file() else None
        views = {r["decl"]: UnitView.from_render(r) for r in _views(src.views)}
        tickets = [_ticket(f"A-{n}{i:03d}", v, src.domain, paper)
                   for i, v in enumerate(views.values())]
        if src.mutants is not None and src.honeypots:
            planted = 0
            used: set[str] = set()
            for m in MutantSet.load(src.mutants).usable:
                if planted >= src.honeypots or m.decl in used or m.decl not in views:
                    continue
                try:
                    hp = honeypot_view(views[m.decl], m)
                except MutantMismatch:
                    continue
                used.add(m.decl)
                planted += 1
                tickets.append(_ticket(f"A-{n}{len(tickets):03d}", hp, src.domain, paper, {
                    "operator": m.operator, "original": m.original, "mutant": m.mutant}))
            counts["honeypots"] += planted
        counts["tickets"] += len(tickets)
        submissions.append({"submission_id": f"S-{src.key}", "title": src.title,
                            "repo_url": src.repo_url, "commit": src.commit,
                            "paper_ref": src.paper_ref, "root": src.root,
                            "tickets": tickets})
    params = CoordParams()
    snapshot = {
        "schema": SCHEMA,
        "notice": {"version": NOTICE_VERSION, "text": NOTICE},
        # The checklist by kind of declaration (dpc.tickets.questions).
        "questions": {kind: [{"id": q, "text": text} for q, text in texts.items()]
                      for kind, texts in TEXTS.items()},
        "purpose": PURPOSE,
        "min_reason_chars": params.min_reason_chars,
        "choice_set_size": params.choice_set_size,
        "submissions": submissions,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                   newline="\n")
    return counts


def default_sources(root: Path, demo_work: Path, case_studies: Path) -> list[Source]:
    fixtures = root / "lean" / "fixtures"
    return [
        Source("mutation", "Mutation fixture (demo)", "https://example.org/mutation", "0" * 40,
               "arithmetic", demo_work / "mutation" / "views.jsonl",
               fixtures / "mutation" / "paper.yaml", demo_work / "mutation" / "mutants.jsonl", 3,
               root="Mut.window"),
        Source("display", "Display rules fixture (demo)", "https://example.org/display", "0" * 40,
               "arithmetic", demo_work / "display" / "views.jsonl",
               fixtures / "display" / "paper.yaml", demo_work / "display" / "mutants.jsonl", 1,
               root="Display.claim"),
        Source("ns", "Navier–Stokes existence and smoothness (Comparator)",
               "https://github.com/openai/NavierStokesAndEuler",
               "f9e8bc5b38b6e212696e8a30e3e91517af887bbd", "analysis",
               case_studies / "ns" / "views.jsonl",
               paper_ref="https://cdn.openai.com/pdf/32d9f210-8b73-45e0-91bc-82a30aef8a9a/"
                         "navier-stokes.pdf",
               root="NavierStokes.Comparator.navier_stokes_breakdown_R3"),
        Source("qrh", "ζ(s) ≠ 0 for Re s > 7/8 (openai/math)", "https://github.com/openai/math",
               "4eaee87548250b2682affda7d05d947c05554bae", "number theory",
               case_studies / "qrh" / "views.jsonl",
               case_studies / "qrh" / "paper.yaml",
               root="OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re"),
    ]
