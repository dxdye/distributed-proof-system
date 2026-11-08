from __future__ import annotations

from dpc.requirements import load_requirements


def test_catalogue_is_complete() -> None:
    reqs = load_requirements()
    assert list(reqs) == [f"SR-{n:02d}" for n in range(1, 61)]


def test_every_requirement_traces_to_a_need() -> None:
    for req in load_requirements().values():
        assert req.needs, req.id
        assert all(1 <= n <= 18 for n in req.needs), req.id
        assert req.text and req.verify
