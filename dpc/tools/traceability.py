"""pytest plugin: requirement markers and the traceability matrix.

Tests declare which requirements they verify::

    @pytest.mark.req("SR-19")
    def test_chain_detects_tampering(): ...

Unknown requirement ids abort the run. With ``--trace-matrix=PATH`` the plugin
writes a Markdown matrix (requirement → tests → status), i.e. the right-hand
side of the V-model, plus a JSON file next to it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from dpc.requirements import Requirement, load_requirements

_links: dict[str, list[str]] = defaultdict(list)  # SR id -> test node ids
_outcomes: dict[str, str] = {}  # node id -> passed | failed | skipped

_ICON = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--trace-matrix",
        default=None,
        metavar="PATH",
        help="write the requirement traceability matrix (Markdown) to PATH",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    known = load_requirements()
    for item in items:
        for marker in item.iter_markers(name="req"):
            for req_id in marker.args:
                if req_id not in known:
                    raise pytest.UsageError(f"{item.nodeid}: unknown requirement {req_id!r}")
                _links[req_id].append(item.nodeid)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when == "call" or report.outcome != "passed":
        previous = _outcomes.get(report.nodeid)
        if previous != "failed":  # a failure in any phase wins
            _outcomes[report.nodeid] = report.outcome


def _status(tests: list[str]) -> str:
    if not tests:
        return "—"
    outcomes = {_outcomes.get(t, "skipped") for t in tests}
    if "failed" in outcomes:
        return _ICON["failed"]
    if len(outcomes) == 1:
        return _ICON[outcomes.pop()]
    return "⚠️ partly skipped"


def render(requirements: dict[str, Requirement]) -> str:
    covered = sum(1 for r in requirements if _links.get(r))
    lines = [
        "# Traceability matrix",
        "",
        f"{covered} of {len(requirements)} requirements are linked to at least one test.",
        "Requirements verified by inspection (I) or demonstration (D) may legitimately",
        "have no automated test.",
        "",
        "| ID | Milestone | V | Status | Tests | Requirement |",
        "|---|---|---|---|---|---|",
    ]
    for req in requirements.values():
        tests = sorted(set(_links.get(req.id, [])))
        names = "<br>".join(f"`{t.split('::', 1)[-1]}`" for t in tests) or ""
        text = req.text if len(req.text) <= 110 else req.text[:107] + "…"
        lines.append(
            f"| {req.id} | {req.milestone} | {','.join(req.verify)} | {_status(tests)} "
            f"| {names} | {text} |"
        )
    return "\n".join(lines) + "\n"


def pytest_sessionfinish(session: pytest.Session) -> None:
    target = session.config.getoption("--trace-matrix")
    if not target:
        return
    requirements = load_requirements()
    path = Path(str(target))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(requirements), encoding="utf-8")
    data = {
        req_id: [{"test": t, "outcome": _outcomes.get(t, "not run")} for t in sorted(set(tests))]
        for req_id, tests in sorted(_links.items())
    }
    path.with_suffix(".json").write_text(json.dumps(data, indent=2), encoding="utf-8")
