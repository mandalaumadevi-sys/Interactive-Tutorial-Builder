"""Typer CLI for the tutorial-builder pipeline."""

from __future__ import annotations

import uuid
from pathlib import Path

import typer
from rich.console import Console

from .config import get_settings
from .graph import build_graph, initial_state

app = typer.Typer(add_completion=False, help="Interactive Tutorial Builder")
console = Console()


def _detect_type(path: Path) -> str:
    return "pptx" if path.suffix.lower() in {".pptx", ".ppt"} else "html"


@app.command()
def info() -> None:
    """Show resolved configuration."""
    s = get_settings()
    console.print(f"[bold]LLM mode:[/] {'mock' if s.use_mock else 'real'}  "
                  f"(api key present: {s.has_api_key})")
    console.print(f"[bold]Text model:[/] {s.text_model}")
    console.print(f"[bold]Vision model:[/] {s.vision_model}")
    console.print(f"[bold]Judge model:[/] {s.judge_model}")
    console.print(f"[bold]MCQ/block:[/] {s.mcq_per_block}  [bold]Final:[/] {s.final_assessment_count}")
    console.print(f"[bold]Runs dir (files):[/] {s.runs_path}")
    db = s.db_url
    where = (db.rsplit("@", 1)[-1] if "@" in db else db) if db else "[red]NOT SET[/]"
    console.print(f"[bold]Supabase Postgres:[/] {'configured · ' + where if db else where}")


@app.command()
def run(
    input_path: str = typer.Argument(..., help="Path to a session .html or .pptx"),
    course: str = typer.Option("Course", help="Course name (memory scope + library folder)"),
    session: str = typer.Option(..., help="Session name (required; library filename)"),
    objectives: str = typer.Option("", help="Comma-separated learning objectives"),
    run_id: str = typer.Option(None, help="Explicit run id (default: random)"),
) -> None:
    """Run the pipeline end-to-end on one session (auto-approves both HITL gates)."""
    path = Path(input_path)
    if not path.exists():
        console.print(f"[red]Input not found:[/] {path}")
        raise typer.Exit(1)

    rid = run_id or uuid.uuid4().hex[:12]
    itype = _detect_type(path)
    metadata = {
        "course_name": course,
        "session_name": session,
        "learning_objectives": [o.strip() for o in objectives.split(",") if o.strip()],
    }
    console.rule(f"Run {rid} · {itype} · {path.name}")

    # State persists in Supabase Postgres via the shared checkpointer (build_graph default).
    graph = build_graph()
    cfg = {"configurable": {"thread_id": rid}}
    graph.invoke(initial_state(rid, str(path), itype, metadata), cfg)

    # Auto-advance through all five human gates (CLI is non-interactive).
    _GATE_ACCEPT = {
        "human_block_review": ("HITL #1 block division", {"blocks_accepted": True}),
        "human_content_review": ("HITL #2 content", {"content_accepted": True}),
        "human_animation_review": ("HITL #3 animation", {"animation_accepted": True}),
        "human_mcq_review": ("HITL #4 MCQs", {"mcq_accepted": True}),
        "human_quality_gate": ("HITL #5 final review", {"review_decision": "approve"}),
    }
    while True:
        snap = graph.get_state(cfg)
        nxt = tuple(snap.next or ())
        if not nxt:
            break
        for gate, (label, patch) in _GATE_ACCEPT.items():
            if gate in nxt:
                console.print(f"[yellow]{label}[/] → auto-accept")
                graph.update_state(cfg, patch)
                break
        graph.invoke(None, cfg)

    final = graph.get_state(cfg).values

    console.rule("Done")
    console.print(f"status: {final.get('status')}")
    console.print(f"blocks: {len(final.get('built_blocks_list', []))}")
    console.print(f"output: {final.get('output_path')}")


@app.command(name="eval")
def eval_golden(
    agent: str = typer.Option("", help="Only this agent (e.g. mcq). Default: all judged agents."),
    limit: int = typer.Option(0, help="Cap examples per label per agent (0 = all). Use a small number for a cheap smoke run."),
) -> None:
    """Golden-set eval: replay the labelled good/bad exemplars through the rubric judge
    (leave-one-out) and report judge accuracy per agent."""
    from rich.table import Table

    from .eval import run_golden_eval

    s = get_settings()
    if s.use_mock:
        console.print("[red]Golden eval needs a real judge.[/] Set TB_LLM_MODE=real + a valid "
                      "OPENROUTER_API_KEY (mock returns canned scores).")
        raise typer.Exit(1)

    agents = [agent] if agent else None
    console.rule("Golden-set evaluation (leave-one-out judge)")

    def _progress(ag, label, ex_id, correct, score):
        mark = "[green]✓[/]" if correct else "[red]✗[/]"
        console.print(f"  {mark} {ag:14} {label:4} {ex_id:18} score={score}")

    report = run_golden_eval(agents, limit=(limit or None), progress=_progress)

    table = Table(title="Judge accuracy vs. golden labels")
    for col in ("Agent", "Examples", "Correct", "Accuracy", "Good→pass", "Bad→fail"):
        table.add_column(col)
    for ag, r in report["agents"].items():
        if "skipped" in r:
            table.add_row(ag, "—", "—", f"[dim]skipped: {r['skipped']}[/]", "—", "—")
            continue
        acc = r["accuracy"]
        acc_str = f"{acc:.0%}" if acc is not None else "—"
        table.add_row(ag, str(r["total"]), str(r["correct"]), acc_str,
                      _pct(r["good_pass_rate"]), _pct(r["bad_fail_rate"]))
    console.print(table)
    o = report["overall"]
    oacc = f"{o['accuracy']:.1%}" if o["accuracy"] is not None else "—"
    console.print(f"[bold]Overall:[/] {o['correct']}/{o['total']} correct  ·  accuracy [bold]{oacc}[/]")


def _pct(v) -> str:
    return f"{v:.0%}" if isinstance(v, (int, float)) else "—"


@app.command(name="deepeval")
def deepeval_cmd(
    agent: str = typer.Option("", help="Only this agent (block_divider|content|visual|mcq|assessment). Default: all."),
    limit: int = typer.Option(0, help="Cap examples per label per agent (0 = all). Use a small number for a cheap smoke run — each example × dimension is one judge call."),
    out: str = typer.Option("", help="Optional path to write the full JSON report."),
) -> None:
    """DeepEval per-agent eval: replay the golden good/bad exemplars through DeepEval GEval
    rubric metrics (+ Faithfulness where source-grounded) and report judge accuracy per agent."""
    import json as _json

    from rich.table import Table

    from .eval.deepeval_harness import GOLDEN_AGENTS, run_deepeval_golden

    s = get_settings()
    if s.use_mock:
        console.print("[red]DeepEval needs a real judge.[/] Set TB_LLM_MODE=real + a valid "
                      "OPENROUTER_API_KEY (mock returns canned scores).")
        raise typer.Exit(1)

    agents = [agent] if agent else GOLDEN_AGENTS
    console.rule("DeepEval per-agent evaluation (GEval rubric + Faithfulness)")
    console.print(f"[dim]judge: {s.judge_model} · agents: {', '.join(agents)}"
                  f"{' · limit ' + str(limit) if limit else ''}[/]")

    def _progress(ag, label, ex_id, correct, score):
        mark = "[green]✓[/]" if correct else "[red]✗[/]"
        console.print(f"  {mark} {ag:14} {label:4} {ex_id:20} score={score}")

    report = run_deepeval_golden(agents, limit=(limit or None), progress=_progress)

    table = Table(title="DeepEval judge accuracy vs. golden labels")
    for col in ("Agent", "Examples", "Correct", "Accuracy", "Good→pass", "Bad→fail"):
        table.add_column(col)
    for ag, r in report["agents"].items():
        if "skipped" in r:
            table.add_row(ag, "—", "—", f"[dim]skipped: {r['skipped']}[/]", "—", "—")
            continue
        acc = r["accuracy"]
        table.add_row(ag, str(r["total"]), str(r["correct"]),
                      f"{acc:.0%}" if acc is not None else "—",
                      _pct(r["good_pass_rate"]), _pct(r["bad_fail_rate"]))
    console.print(table)
    o = report["overall"]
    oacc = f"{o['accuracy']:.1%}" if o["accuracy"] is not None else "—"
    console.print(f"[bold]Overall:[/] {o['correct']}/{o['total']} correct  ·  accuracy [bold]{oacc}[/]")

    if out:
        Path(out).write_text(_json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[dim]full report → {out}[/]")


@app.command(name="deepeval-e2e")
def deepeval_e2e_cmd(
    run_dir: str = typer.Option("", help="A runs/<id>/ dir containing input.html + *tutorial.html."),
    source: str = typer.Option("", help="Source session .html (use with --tutorial instead of --run-dir)."),
    tutorial: str = typer.Option("", help="Finished tutorial .html (use with --source)."),
    out: str = typer.Option("", help="Optional path to write the full JSON report."),
) -> None:
    """DeepEval end-to-end: score one finished tutorial against its source session via the
    session-level final_quality rubric + a Faithfulness check."""
    import json as _json

    from rich.table import Table

    from .eval.deepeval_harness import run_deepeval_e2e

    s = get_settings()
    if s.use_mock:
        console.print("[red]DeepEval needs a real judge.[/] Set TB_LLM_MODE=real + a valid key.")
        raise typer.Exit(1)

    kwargs: dict = {}
    if run_dir:
        kwargs["run_dir"] = run_dir
    elif source and tutorial:
        kwargs["source_html"] = Path(source).read_text(encoding="utf-8")
        kwargs["tutorial_html"] = Path(tutorial).read_text(encoding="utf-8")
    else:
        console.print("[red]Provide --run-dir, or both --source and --tutorial.[/]")
        raise typer.Exit(1)

    console.rule("DeepEval end-to-end (final_quality rubric + Faithfulness)")
    console.print(f"[dim]judge: {s.judge_model}[/]")
    report = run_deepeval_e2e(**kwargs)

    table = Table(title=f"Tutorial: {report['tutorial']}  (threshold {report['threshold']}/10)")
    for col in ("Dimension", "Score/10", "Pass", "Reason"):
        table.add_column(col)
    for d in report["dimensions"]:
        mark = "[green]✓[/]" if d["passed"] else "[red]✗[/]"
        table.add_row(d["dimension"], str(d["score"]), mark, (d["reason"] or "")[:80])
    for r in report["rag"]:
        mark = "[green]✓[/]" if r["passed"] else "[red]✗[/]"
        table.add_row(f"[cyan]{r['metric']}[/]", str(r["score"]), mark, (r["reason"] or "")[:80])
    console.print(table)
    verdict = "[green]PASS[/]" if report["passed"] else "[red]FAIL[/]"
    console.print(f"[bold]Weighted:[/] {report['weighted_score']}/10  ·  overall {verdict}")

    if out:
        Path(out).write_text(_json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[dim]full report → {out}[/]")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the web app (upload → run → review block division → review final → download)."""
    import uvicorn
    console.print(f"[bold green]Tutorial Builder[/] → http://{host}:{port}")
    uvicorn.run("tutorial_builder.api.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
