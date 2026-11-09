"""Checking Lean evidence files against the fixed commit (SR-10).

A reviewer may back an "incorrect" verdict with a Lean file (SR-09). The file
is foreign code: it is compiled with the plain ``lean`` binary inside the
sandbox, then ``dpc-evidence`` (our own code, no initializers) replays its
declarations through the kernel, checks the axioms and, for vacuity, that it
proves exactly the vacuity goal of the target declaration.

Contract for evidence files: module ``DpcEvidence``, main theorem
``dpc_evidence``; for vacuity of ``T : ∀ xs, C`` the statement is
``∀ xs, False`` (``evidence_template`` writes the skeleton).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EVIDENCE_MODULE = "DpcEvidence"
EVIDENCE_THEOREM = "dpc_evidence"
EVIDENCE_FILE = f"{EVIDENCE_MODULE}.lean"
MAX_OUTPUT = 4000


@dataclass(frozen=True)
class EvidenceCheck:
    ok: bool  # compiles, kernel-checked, standard axioms only
    confirms: bool  # proves the claim by machine (vacuity with the exact goal)
    reason: str
    axioms: tuple[str, ...] = ()
    output: str = ""  # compiler messages (truncated)

    @classmethod
    def from_file(cls, path: Path, output: str = "") -> EvidenceCheck:
        data = json.loads(path.read_text("utf-8"))
        return cls(bool(data["ok"]), bool(data["confirms"]), str(data["reason"]),
                   tuple(data.get("axioms", ())), output[-MAX_OUTPUT:])

    @classmethod
    def failed(cls, reason: str, output: str = "") -> EvidenceCheck:
        return cls(False, False, reason, (), output[-MAX_OUTPUT:])

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "confirms": self.confirms, "reason": self.reason,
                "axioms": list(self.axioms)}


def evidence_template(root_module: str, target: str, kind: str) -> str:
    """Skeleton shown to reviewers."""
    if kind == "vacuity":
        hint = f"the binders of {target}, with its conclusion replaced by False"
    else:
        hint = "a statement that exhibits the problem"
    return (f"import {root_module}\n\n-- {hint}\n"
            f"theorem {EVIDENCE_THEOREM} : _ := by\n  sorry\n")
