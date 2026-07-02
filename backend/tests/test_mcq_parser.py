from tutorial_builder.tools.mcq_parser import parse_mcq_text

SAMPLE = """TOPIC: SDLC
SUB_TOPIC: Waterfall
QUESTION_KEY: q1
QUESTION_TEXT: Which best describes the Waterfall model
QUESTION_TYPE: SINGLE_MULTIPLE_CHOICE
CODE: NA
OPTION_1: Sequential phases with little overlap
OPTION_2: Continuous iteration every two weeks
OPTION_3: No planning is required
OPTION_4: Testing happens before design
CORRECT_OPTION: OPTION_1
EXPLANATION: Waterfall runs phases sequentially
BLOOM_LEVEL: UNDERSTAND
LEARNING_OUTCOME: understand_waterfall
-END-"""


def test_parses_single_choice():
    mcqs = parse_mcq_text(SAMPLE)
    assert len(mcqs) == 1
    m = mcqs[0]
    assert m.multi is False
    assert m.correct_indexes == [0]
    assert len(m.options) == 4
    assert m.to_quiz_entry()["correctIndexes"] == [0]


def test_multi_choice_detected():
    txt = SAMPLE.replace("QUESTION_TYPE: SINGLE_MULTIPLE_CHOICE",
                         "QUESTION_TYPE: MORE_THAN_ONE_MULTIPLE_CHOICE") \
                .replace("CORRECT_OPTION: OPTION_1", "CORRECT_OPTION: OPTION_1, OPTION_2")
    m = parse_mcq_text(txt)[0]
    assert m.multi is True
    assert m.correct_indexes == [0, 1]
