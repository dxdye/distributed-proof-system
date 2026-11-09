"""Local demo (M4): the mutation fixture as a reviewable submission."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dpc.audit import AuditLog
from dpc.coord import BlobStore, Coordinator, CoordParams, Vault
from dpc.coord.demo import seed_demo
from dpc.lean.executor import HostExecutor


def test_parameter_overrides() -> None:
    params = CoordParams.from_overrides({"reveal_batch": 1, "decision": {"k_min": 2}})
    assert params.reveal_batch == 1 and params.decision.k_min == 2 and params.parallel == 3
    with pytest.raises(ValueError, match="unknown"):
        CoordParams.from_overrides({"k_min": 2})


@pytest.mark.lean
@pytest.mark.req("SR-05", "SR-06", "SR-21")
def test_demo_seeds_a_reviewable_submission(tmp_path: Path, host_executor: HostExecutor) -> None:
    coord = Coordinator(AuditLog(tmp_path / "log.sqlite"), Vault(tmp_path / "vault.sqlite"),
                        blobs=BlobStore(tmp_path / "blobs"), rng=np.random.default_rng(0))
    info = seed_demo(coord, tmp_path / "work", host_executor, share=0.2)
    assert info["units"] == 10 and info["tickets"] == 12
    views = [t.view for t in coord.state.tickets.values()]
    honeypots = [t for t in coord.state.tickets.values() if coord.vault.is_honeypot(t.ticket_id)]
    assert len(honeypots) == 2
    for hp in honeypots:  # a honeypot differs from the real ticket of its unit in one component
        real = next(v for v in views if v.declaration == hp.view.declaration and v != hp.view)
        changed = [a for a, b in zip(real.components, hp.view.components, strict=True)
                   if a.text != b.text]
        assert len(changed) == 1
