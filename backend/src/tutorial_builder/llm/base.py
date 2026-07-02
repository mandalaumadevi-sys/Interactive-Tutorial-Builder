"""Shared LLM helpers: image encoding + best-effort JSON extraction."""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any


def encode_image_data_url(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def as_object(data: Any) -> dict:
    """Coerce a parsed JSON result to a single object.

    Real models sometimes wrap their object in an array (e.g. ``[{...}]``); callers that
    expect a dict use this to stay robust. Returns the first dict found, else ``{}``.
    """
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for element in data:
            if isinstance(element, dict):
                return element
    return {}


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model response (tolerant of prose/fences)."""
    text = (text or "").strip()
    m = _JSON_FENCE.search(text)
    candidate = m.group(1).strip() if m else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(candidate)):
            c = candidate[i]
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(candidate[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}")
