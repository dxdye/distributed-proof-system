from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dpc.audit import CanonicalJSONError, canonical_json

pytestmark = pytest.mark.req("SR-19")

valid_text = st.text(alphabet=st.characters(exclude_categories=["Cs"]))
bmp_keys = st.text(alphabet=st.characters(max_codepoint=0xFFFF, exclude_categories=["Cs"]))
json_scalars = st.none() | st.booleans() | st.integers(-(2**53), 2**53) | valid_text
json_values = st.recursive(
    json_scalars,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(bmp_keys, inner, max_size=4),
    max_leaves=20,
)


def test_sorted_keys_and_no_whitespace() -> None:
    assert canonical_json({"b": 1, "a": [True, None, "x"]}) == b'{"a":[true,null,"x"],"b":1}'


def test_utf8_is_not_escaped() -> None:
    text = "Navier–Stokes ℝ³"
    assert canonical_json({"name": text}) == ('{"name":"' + text + '"}').encode()


@pytest.mark.parametrize(
    "value",
    [
        1.5, {"x": 0.0}, [float("nan")], 2**53 + 1, {1: "non-string key"}, b"bytes",
        {"𝔸": 1}, "\ud800", {"\udfff": 1},
    ],
)
def test_rejects_ambiguous_values(value: Any) -> None:
    with pytest.raises(CanonicalJSONError):
        canonical_json(value)


@given(json_values)
def test_roundtrip_and_idempotence(value: Any) -> None:
    encoded = canonical_json(value)
    decoded = json.loads(encoded)
    assert decoded == value
    assert canonical_json(decoded) == encoded


@given(st.dictionaries(bmp_keys, st.integers(0, 9), max_size=6))
def test_insertion_order_does_not_matter(value: dict[str, int]) -> None:
    reordered = dict(reversed(list(value.items())))
    assert canonical_json(value) == canonical_json(reordered)
