"""Hashtags of a submission (proposal C-44).

A tag names the problem a submission is about (``navier-stokes``,
``erdos-problems``) or its kind (``counterexample``), so that it is found
quickly on the progress page and in the discussions. Maintainers set them.
They are not a preference for the draw: a tag can name a single paper, and
choosing tickets by paper would allow targeting them (C-32).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

#: Lower-case letters, digits and inner hyphens; 2 to 40 characters.
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$")
#: More would not help finding anything.
MAX_TAGS = 12


def normalize_tag(raw: str) -> str:
    """``#Erdős Problems`` → ``erdos-problems``. Raises ``ValueError`` if what
    remains is not a tag."""
    text = unicodedata.normalize("NFKD", raw.strip().lstrip("#").strip())
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[\s_]+", "-", text)
    if not TAG.match(text) or "--" in text:
        raise ValueError(f"not a tag: {raw!r} (letters a-z, digits and inner hyphens, "
                         "2 to 40 characters)")
    return text


def normalize_tags(raw: Iterable[str]) -> tuple[str, ...]:
    """Each tag normalized and once, in the given order; empty entries dropped."""
    out: list[str] = []
    for item in raw:
        if not item.strip().lstrip("#").strip():
            continue
        tag = normalize_tag(item)
        if tag not in out:
            out.append(tag)
    if len(out) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags per submission")
    return tuple(out)
