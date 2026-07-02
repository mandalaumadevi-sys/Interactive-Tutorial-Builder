"""End-to-end smoke test on the mock LLM (no key, no cost)."""
import uuid

from tutorial_builder.graph import build_graph, initial_state

# Flat <h1> headings — mirrors real curriculum exports (no h2/h3 hierarchy).
SAMPLE = """<html><body>
<h1>Software Development Models</h1><p>Why teams need different development models.</p>
<h1>Why One SDLC Doesn't Fit All</h1><p>Different projects have different constraints.</p>
<h1>Waterfall Model</h1><p>The waterfall model runs phases sequentially.</p>
<img src='waterfall.png' alt='waterfall model diagram'>
<h1>Agile Model</h1><p>Agile delivers software iteratively in short cycles.</p>
<h1>Popular Agile Frameworks</h1><p>Scrum and Kanban are common Agile frameworks.</p>
<h1>V-Model</h1><p>The V-model pairs each development phase with a testing phase.</p>
</body></html>"""


def test_full_pipeline_mock(tmp_path):
    f = tmp_path / "session.html"
    f.write_text(SAMPLE, encoding="utf-8")
    graph = build_graph()  # MemorySaver
    cfg = {"configurable": {"thread_id": uuid.uuid4().hex[:8]}}
    meta = {"course_name": "C", "session_name": "SDLC Models"}
    graph.invoke(initial_state("t1", str(f), "html", meta), cfg)

    # advance all five human gates (auto-accept / auto-approve)
    accept = {
        "human_block_review": {"blocks_accepted": True},
        "human_content_review": {"content_accepted": True},
        "human_animation_review": {"animation_accepted": True},
        "human_mcq_review": {"mcq_accepted": True},
        "human_assessment_review": {"assessment_accepted": True},
    }
    gates_seen = []
    for _ in range(12):
        snap = graph.get_state(cfg)
        nxt = tuple(snap.next or ())
        if not nxt:
            break
        for gate, patch in accept.items():
            if gate in nxt:
                gates_seen.append(gate)
                graph.update_state(cfg, patch)
                break
        graph.invoke(None, cfg)

    vals = graph.get_state(cfg).values
    assert vals.get("status") == "completed"
    assert vals.get("final_html") and "QUIZ_DATA" in vals["final_html"]
    # default target is 4–5 blocks (TB_MIN_BLOCKS / TB_MAX_BLOCKS)
    assert 4 <= len(vals.get("built_blocks_list", [])) <= 5
    # all five gates were exercised, in order
    assert gates_seen == ["human_block_review", "human_content_review",
                          "human_animation_review", "human_mcq_review", "human_assessment_review"]
    # per-stage advisory metrics were attached for the animation + mcq gates (the content gate no
    # longer surfaces an eval score — the reviewer reads the rendered blocks directly)
    assert {"visual", "mcq"} <= set(vals.get("eval_scores", {}))
