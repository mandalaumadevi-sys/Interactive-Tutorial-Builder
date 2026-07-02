"""Structured per-run logging (JSONL) + a console echo."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunLogger:
    """Appends JSONL events for a run to ``<runs>/<run_id>/log.jsonl``."""

    def __init__(self, run_id: str, runs_dir: Path):
        self.run_id = run_id
        self.dir = Path(runs_dir) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "log.jsonl"

    def log(self, event: str, **data: Any) -> None:
        self.emit(event, **data)

    def emit(self, event: str, stage: str = "", **data: Any) -> None:
        rec = {"ts": round(time.time(), 3), "run_id": self.run_id,
               "event": event, "stage": stage, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        msg = f"[bold cyan]{data.get('node', stage) or event}[/] {event}"
        preview = {k: v for k, v in data.items() if k not in {"html", "content_html"}}
        if preview:
            msg += f"  [dim]{json.dumps(preview, default=str)[:160]}[/]"
        console.print(msg)
