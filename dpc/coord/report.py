"""A report on one submission (concept §11.1 and §16 point 7; SR-17, SR-42, SR-47).

Simple and unsigned, for the pilot: Markdown built from the public data of the
progress page (:mod:`dpc.coord.progress`), so it shows nothing the page does
not show (C-26), plus the head of the audit log it was built from. Whoever has
the log can check it (``dpc audit-verify --head``) and build the same report
again (``dpc report``). Reports are always published, negative ones and those
of closed submissions too (SR-47).

Not yet: the signature (SR-17), class B and the certificate (§7), definition
tests, errata (§13.6). The report says so instead of leaving them out.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from dpc.coord import progress

if TYPE_CHECKING:
    from dpc.coord.service import Coordinator

STATE_LABELS = {"accepted": "accepted", "error": "error confirmed",
                "in review": "in review", "not started": "not started"}


def _date(value: str | datetime | None) -> str:
    if value is None:
        return "—"
    at = datetime.fromisoformat(value) if isinstance(value, str) else value
    return at.strftime("%Y-%m-%d")


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _findings(coord: Coordinator, submission_id: str, units: list[dict[str, Any]]) -> list[str]:
    """Confirmed errors of real declarations. The confirmed justification is
    quoted once the discussion is open, i.e. after every planted error of the
    paper is revealed; before, a quote could be compared with open copies."""
    st = coord.state
    out = []
    for u in units:
        if u["state"] != "error":
            continue
        line = f"- `{u['declaration']}`: error confirmed on {_date(u['decided_at'])}."
        if coord.thread_open(submission_id, u["declaration"]):
            unit = next(x for x in progress.units(coord, submission_id)
                        if x.declaration == u["declaration"])
            for cid in unit.real.claims:
                claim = st.claims[cid]
                if claim.status != "confirmed":
                    continue
                review = st.reviews[claim.review_seq]
                line += f"\n  > {_cell(review.reason)}"
                if review.evidence is not None:
                    line += (f"\n  Evidence ({review.evidence.kind}): "
                             f"`{review.evidence.file_sha256[:16]}…`")
        else:
            line += " The justification is published with the discussion, once the planted " \
                    "errors of this paper are revealed."
        out.append(line)
    return out or ["- None confirmed."]


def _basis(d: dict[str, Any]) -> list[str]:
    b, defs = d["basis"], d["library_definitions"]
    if b is None:
        return ["Not recorded for this submission."]
    lines = []
    if b["replayed"]:
        lines.append(f"- **Own proofs:** {_num(b['modules_replayed'])} modules with "
                     f"{_num(b['constants_replayed'])} declarations re-checked by Lean's kernel, "
                     f"{b['replay_failures'] or 'none'} rejected.")
    else:
        lines.append("- **Own proofs:** not re-checked by the kernel for this submission.")
    lines.append(f"- **Axioms:** {', '.join(b['axioms'])}, the standard ones only.")
    mathlib = next((lib for lib in b["libraries"] if lib["name"] == "mathlib"), None)
    if mathlib is not None:
        others = len(b["libraries"]) - 1
        text = f"- **Mathlib** `{mathlib['rev'][:12]}`"
        text += f" and {others} further official packages" if others else ""
        text += ": from their official sources"
        if b["hardened_unchanged"]:
            files = f" ({_num(b['hardened_files'])} files compared)" if b["hardened_files"] else ""
            text += f", unchanged by the build{files}"
        text += (". Re-checked by the kernel." if b["libraries_replayed"]
                 else ". Not re-checked here: trusted as far as Mathlib's own checks.")
        lines.append(text)
    lines.append(f"- **Lean's kernel** {b['toolchain']}: "
                 + ("confirmed by a second, independent kernel." if b["second_kernel"]
                    else "trusted; no second kernel has checked this result yet."))
    if defs is None:
        lines.append("- **Library definitions the statements use:** listed once the planted "
                     "errors of this paper are revealed.")
    else:
        reviewed = sum(1 for g in defs if g["reviewed"])
        lines.append(f"- **Library definitions the statements use:** {len(defs)}, of them "
                     f"{reviewed} reviewed themselves. Their use is checked in every review "
                     "(C-27).")
        for g in defs:
            note = f" Convention: {g['note']}" if g["note"] else ""
            lines.append(f"  - `{g['name']}` ({'Mathlib' if g['origin'] == 'library' else 'Lean'})"
                         f".{note}")
    return lines


def render(coord: Coordinator, submission_id: str) -> str:
    """The report as of the coordinator's clock, from the public view."""
    d = progress.detail(coord, submission_id, None)
    head = coord.log.head()
    units = d["units"]
    if d["closed"]:
        kind = "Final report (the submission is closed)"
    elif d["declarations"] and d["decided"] == d["declarations"]:
        kind = "Report (class A complete)"
    else:
        kind = "Interim report"
    forecast = d["forecast"]
    lines = [
        f"# Review report: {d['title']}",
        "",
        f"{kind} as of {_date(coord.now())} · audit log entry {head.seq if head else '—'}, "
        f"head `{head.hash[:16] if head else '—'}` · not signed (pilot)",
        "",
        "| | |",
        "|---|---|",
        f"| Main theorem | `{d['root']}` |" if d["root"] else "| Main theorem | not named |",
        f"| Repository | {d['repo_url']} @ `{d['commit']}` |",
        f"| Paper | {d['paper_url'] or d['paper_ref'] or '—'} |",
        f"| Readiness | PRL {d['prl']}: {d['prl_meaning']} |",
        f"| Class A | {d['decided']} of {d['declarations']} declarations decided: "
        f"{d['accepted']} accepted, {d['errors']} with a confirmed error, "
        f"{d['in_review']} in review, {d['not_started']} not started |",
        "| Residual error | "
        + (f"{d['residual_error']:.1e}, an estimate of the probability that an accepted "
           "declaration is wrong |" if d["residual_error"] is not None else "none accepted yet |"),
        "| Forecast | "
        + (f"class A decided with 50 % in {forecast['p50_weeks']:.0f} weeks, with 85 % in "
           f"{forecast['p85_weeks']:.0f} weeks |" if forecast else "not measured yet |"),
        "| Class B | not run yet: proof internals are checked by the kernel only |",
        "",
        "The share decided counts the repository's own statements and definitions. The Mathlib "
        "definitions they use are not counted; see below.",
        "",
        "## The main statement",
        "",
    ]
    if d["main_statement"]:
        lines += [f"The paper says ({d['main_locator'] or 'no locator'}):", "",
                  f"> {_cell(d['main_statement'])}", ""]
    else:
        lines += ["No passage of the paper is mapped to the main theorem yet.", ""]
    view = d["main_view"]
    if view is not None:
        lines += ["Lean says:", "", "```lean"]
        lines += [c.get("trusted_text") or c["text"] for c in view["components"]
                  if c["target"] == "type"]
        lines += ["```", ""]
    else:
        lines += ["The formal statement is published once it is decided and the planted errors "
                  "of this paper are revealed.", ""]
    lines += ["## What the result relies on", "", *_basis(d), "",
              "## Class A, declaration by declaration", "",
              "| Declaration | Kind | Domain | State | Decided |", "|---|---|---|---|---|"]
    lines += [f"| `{u['declaration']}` | {u['decl_kind']} | {u['domain']} | "
              f"{STATE_LABELS.get(u['state'], u['state'])} | {_date(u['decided_at'])} |"
              for u in units]
    lines += ["", "## Findings", "", *_findings(coord, submission_id, units), ""]
    if d["notes"]:
        lines += ["## Notes by the maintainers", ""]
        lines += [f"- {_date(n['at'])}: {_cell(n['text'])}"
                  for n in sorted(d["notes"], key=lambda n: str(n["at"])) if not n["hidden"]]
        lines.append("")
    lines += [
        "## Checking this report",
        "",
        "Every figure is a projection of the public audit log. Planted errors are not "
        "listed while any of them is unrevealed, and open work shows no verdicts.",
        "",
        "```",
        f"dpc audit-verify <log> --head {head.hash if head else '<head>'}",
        f"dpc report {submission_id} --data <data directory>",
        "```",
        "",
        "Not yet in this report: the signature (SR-17), class B and its certificate, definition "
        "tests and errata.",
        "",
    ]
    return "\n".join(lines)
