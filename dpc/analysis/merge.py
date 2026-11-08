"""Cross-check of the two analyzer runs (docs/adr/0004).

The ``core`` run executes no foreign code and is authoritative. The
``metadata`` run loads environment extensions — running the analysed
repository's ``initialize`` blocks — and could therefore be tampered with. It
may only *add* presentation data (source ranges, flags, refined ticket units);
any disagreement on substance is reported as a mismatch.
"""

from __future__ import annotations

from dpc.analysis.model import Analysis, Decl

_SUBSTANCE = (
    "decl_kind",
    "module",
    "hardened",
    "in_tcb",
    "tcb_deps",
    "all_deps",
    "type_hash",
    "value_hash",
    "proof_hash",
)


class AnalysisMismatch(ValueError):
    """Core and metadata run disagree — treat the repository as hostile."""


def merge(core: Analysis, metadata: Analysis) -> Analysis:
    if core.header.mode != "core" or metadata.header.mode != "metadata":
        raise ValueError("expected one core and one metadata analysis")
    for field in ("root", "imports", "toolchain", "hardened_prefixes", "axioms"):
        if getattr(core.header, field) != getattr(metadata.header, field):
            raise AnalysisMismatch(f"header field {field!r} differs")
    if core.decls.keys() != metadata.decls.keys():
        missing = sorted(core.decls.keys() ^ metadata.decls.keys())[:5]
        raise AnalysisMismatch(f"declaration sets differ, e.g. {missing}")
    merged: dict[str, Decl] = {}
    for name, c in core.decls.items():
        m = metadata.decls[name]
        for field in _SUBSTANCE:
            if getattr(c, field) != getattr(m, field):
                raise AnalysisMismatch(f"{name}: field {field!r} differs")
        unit = m.unit if _valid_unit(core, m.unit) else c.unit
        merged[name] = c.model_copy(update={"unit": unit, "range": m.range, "flags": m.flags})
    return Analysis(metadata.header, merged)


def _valid_unit(core: Analysis, unit: str) -> bool:
    target = core.decls.get(unit)
    return target is not None and not target.hardened
