"""Filesystem helpers: prompts, skills, eval-set loading, run directories, HTML→text."""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

from ..config import Settings, get_settings


def read_agent_prompt(name: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return (settings.package_prompts_path / f"{name}.md").read_text(encoding="utf-8")


def read_skill(name: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return (settings.package_skills_path / f"{name}.md").read_text(encoding="utf-8")


def read_mcq_prompt(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.mcq_prompt_file.read_text(encoding="utf-8")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_visual_decision_examples(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    base = settings.eval_sets_path / "visual-decision"
    return {
        "animate": _load_json(base / "animate_examples.json", []),
        "skip": _load_json(base / "skip_examples.json", []),
    }


def load_agent_evalset(agent: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    base = settings.eval_sets_path / agent
    return {
        "rubric": _load_json(base / "rubric.json", None),
        "good": _load_json(base / "good_examples.json", []),
        "bad": _load_json(base / "bad_examples.json", []),
    }


def dimension_id(d: dict) -> str:
    """Read a rubric/score dimension's identifier across rubric schema variants.

    Supports both the legacy shape (``{"dimension": "..."}``) and the richer shape
    (``{"id": "...", "name": "..."}``). Returns ``"?"`` if none is present.
    """
    return d.get("dimension") or d.get("id") or d.get("name") or "?"


def html_to_text(html: str) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)


def run_dir(run_id: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    d = settings.runs_path / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in (s or "")).strip("_") or "x"
