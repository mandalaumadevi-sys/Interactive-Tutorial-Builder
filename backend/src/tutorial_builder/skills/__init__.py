"""Agent skills: house-style + animation-pattern references, and the MCQ validator."""

from __future__ import annotations

from ..utils.io import read_skill
from .assessment_validator import validate_assessment
from .mcq_validator import validate


def house_style() -> str:
    return read_skill("house_style")


def visual_patterns() -> str:
    return read_skill("visual_patterns")


__all__ = ["house_style", "visual_patterns", "validate", "validate_assessment"]
