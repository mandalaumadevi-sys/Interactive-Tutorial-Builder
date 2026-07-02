"""Offline evaluation harnesses (golden-set regression for the LLM-as-judge)."""

from .golden import run_golden_eval

__all__ = ["run_golden_eval"]
