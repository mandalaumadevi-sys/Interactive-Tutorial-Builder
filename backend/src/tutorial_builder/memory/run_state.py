"""Intra-run memory helpers — derive cross-agent context from accumulated artifacts."""

from __future__ import annotations

from ..schemas import MCQ, BlockResult


def mcq_topics(mcqs: dict[int, list[MCQ]]) -> list[str]:
    """Topics/learning-outcomes already covered by per-block MCQs (Agent 4 avoids repeats)."""
    topics: list[str] = []
    for qs in mcqs.values():
        for m in qs:
            lo = (m.learning_outcome or m.meta.get("learning_outcome")
                  or m.meta.get("sub_topic"))
            if lo and lo not in topics:
                topics.append(lo)
    return topics


def defined_concepts(blocks: list[BlockResult]) -> list[str]:
    """Concepts introduced this session (titles + Agent-1 concepts) — fed to cross-session memory."""
    concepts: list[str] = []
    for b in blocks:
        if b.title:
            concepts.append(b.title)
        concepts.extend(b.concepts_defined)
    seen, out = set(), []
    for c in concepts:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out
