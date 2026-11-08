"""Verifying the hardened set H against its provenance.

The analyzer marks a declaration as hardened by the root namespace of its
module (`Mathlib`, `Init`, …). A submission could place its own modules under
such a namespace (e.g. a file `Mathlib/Evil.lean` in a non-official package)
and thereby remove definitions from TCB_new. This check accepts a hardened
module only if it is actually shipped by the toolchain or by an official
package at the pinned revision.
"""

from __future__ import annotations

from collections.abc import Mapping

from dpc.analysis.model import Analysis

CORE = "core"


def unverified_hardened_modules(
    analysis: Analysis, official: Mapping[str, frozenset[str]]
) -> list[str]:
    """Modules marked hardened that no official source provides (should be empty)."""
    known: set[str] = set()
    for modules in official.values():
        known |= modules
    return sorted(
        {
            d.module
            for d in analysis.decls.values()
            if d.hardened and d.module is not None and d.module not in known
        }
    )
