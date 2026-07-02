"""Turn a course's accumulated review feedback into *standing guidance* that is injected into the
generation prompts on every future run of that course.

The point: a reviewer should only ever have to give a correction once. After they do, it is saved
to course memory (tagged by the stage it came from), and on the next run that correction is fed
back to the relevant agent automatically — so the same input is never required again and the
workflow self-refines. See ``cross_session`` for where the feedback is persisted.

Feedback is stored tagged by stage, e.g. ``[content b2] use simpler wording`` or
``[mcq 1:0] options too long`` or a raw (untagged) string for block-division notes. This module
buckets those tags back to the stage they should guide.
"""

from __future__ import annotations

# stage kind -> the tag prefix its feedback entries carry in course memory
_KIND_TAGS = {"content": "[content", "animation": "[animation", "mcq": "[mcq", "assessment": "[assessment"}
_ALL_TAGS = tuple(_KIND_TAGS.values())
_MAX_ITEMS = 12  # keep the injected prompt bounded — most-recent corrections win


def _entries(memory: dict | None) -> list[str]:
    return [str(f).strip() for f in ((memory or {}).get("feedback") or []) if str(f).strip()]


def _strip_tag(s: str) -> str:
    """Drop a leading ``[stage bN]`` / ``[mcq b:i]`` tag, leaving the human-written guidance."""
    return s.split("]", 1)[1].strip() if s.startswith("[") and "]" in s else s


def standing_guidance(memory: dict | None, kind: str) -> str:
    """Return a prompt block of prior corrections relevant to ``kind`` (one of
    content/animation/mcq/assessment/division), or ``""`` when there are none.

    ``division`` collects the *untagged* feedback (block-division notes); the other kinds collect
    entries carrying their own tag."""
    picked: list[str] = []
    for s in _entries(memory):
        low = s.lower()
        if kind == "division":
            if low.startswith(_ALL_TAGS):  # tagged stage feedback is not division guidance
                continue
            body = s
        else:
            tag = _KIND_TAGS.get(kind)
            if not tag or not low.startswith(tag):
                continue
            body = _strip_tag(s)
        body = body.strip()
        if not body or body.lower() == "rejected":  # a bare "rejected" note isn't actionable guidance
            continue
        picked.append(body)

    seen: set[str] = set()
    uniq: list[str] = []
    for p in reversed(picked):  # most-recent first, then de-dupe
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    if not uniq:
        return ""
    uniq = uniq[:_MAX_ITEMS]
    return (
        "STANDING REVIEWER GUIDANCE for this course — these are corrections from earlier reviews. "
        "Apply them automatically now so they never need to be repeated:\n- " + "\n- ".join(uniq)
    )
