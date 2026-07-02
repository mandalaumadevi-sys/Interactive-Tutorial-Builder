from tutorial_builder.assembler import html_assembler
from tutorial_builder.schemas import MCQ, AssessmentQuestion, BlockResult


def _mcq(q):
    return MCQ(question=q, options=["a", "b", "c", "d"], multi=False,
              correctIndexes=[0], explanation="because a")


def test_render_produces_quiz_data_and_steps():
    blocks = [BlockResult(block_id=1, title="Intro", content_html="<div class='main-content'><p>hi</p></div>")]
    mcqs = {1: [_mcq("q1")]}
    final = [AssessmentQuestion(question="Explain the core idea?",
                               answer="The core idea is that each phase informs the next.",
                               bloom_level="Understand")]
    html = html_assembler.render(session_title="T", blocks=blocks, mcqs=mcqs, final_assessment=final)
    assert "QUIZ_DATA" in html and "</html>" in html
    assert 'data-kind="assessment"' in html          # descriptive assessment carousel
    assert "Model answer" in html                    # answer shown on the card
    assert "quiz-area-0" in html                     # per-block MCQ quiz wired
    assert "Intro" in html
