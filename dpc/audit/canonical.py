"""Canonical JSON for hashing and signing.

A strict subset of RFC 8785 (JSON Canonicalization Scheme): keys sorted, no
insignificant whitespace, UTF-8 output.

Deliberate restrictions, so that every value has exactly one encoding:

* **No floats.** Float formatting differs between languages and versions; a
  hash must never depend on it. Store integers (e.g. seconds, basis points) or
  decimal strings instead.
* **Integers must fit into an IEEE double exactly** (|n| <= 2**53), as RFC 8785
  requires for interoperability with other implementations.
* **Object keys are restricted to the Basic Multilingual Plane.** RFC 8785
  sorts keys by UTF-16 code units, Python by code points; the two orders agree
  on BMP strings.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

MAX_SAFE_INT = 2**53


class CanonicalJSONError(ValueError):
    """The value cannot be encoded canonically."""


def _has_lone_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if _has_lone_surrogate(value):
            raise CanonicalJSONError(f"lone surrogate in string at {path} (not valid UTF-8)")
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise CanonicalJSONError(f"integer out of safe range at {path}")
        return
    if isinstance(value, float):
        raise CanonicalJSONError(f"float at {path}: use an integer or a decimal string")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(f"non-string key {key!r} at {path}")
            if any(ord(ch) > 0xFFFF for ch in key) or _has_lone_surrogate(key):
                raise CanonicalJSONError(f"key outside the BMP or invalid at {path}")
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise CanonicalJSONError(f"unsupported type {type(value).__name__} at {path}")


def canonical_json(value: Any) -> bytes:
    """Encode `value` canonically (see module docstring)."""
    _check(value, "$")
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
