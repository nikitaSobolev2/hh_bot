"""Unit tests for interview preparation AI prompts and parsers."""


def test_build_preparation_guide_prompt_contains_vacancy_title():
    from src.services.ai.prompts import build_preparation_guide_prompt

    prompt = build_preparation_guide_prompt(
        vacancy_title="Backend Developer",
        vacancy_description="Looking for experienced dev",
        user_tech_stack=["Python", "FastAPI"],
        user_work_experience="5 years at ACME",
    )

    assert "Backend Developer" in prompt
    assert "Python" in prompt
    assert "[PrepStepStart]" in prompt


def test_build_preparation_guide_prompt_without_description():
    from src.services.ai.prompts import build_preparation_guide_prompt

    prompt = build_preparation_guide_prompt(
        vacancy_title="Frontend Developer",
        vacancy_description=None,
        user_tech_stack=[],
        user_work_experience="",
    )

    assert "Frontend Developer" in prompt


def test_build_deep_learning_summary_prompt_contains_step_title():
    from src.services.ai.prompts import build_deep_learning_summary_prompt

    prompt = build_deep_learning_summary_prompt(
        step_title="SQL Optimization",
        step_content="Basic SQL knowledge needed",
        vacancy_context="Data engineering role",
    )

    assert "SQL Optimization" in prompt
    assert "Data engineering role" in prompt


def test_build_preparation_test_prompt_contains_format_markers():
    from src.services.ai.prompts import build_preparation_test_prompt

    prompt = build_preparation_test_prompt(
        step_title="Algorithms",
        step_content="Study sorting algorithms",
        deep_summary=None,
    )

    assert "[TestStart]" in prompt
    assert "[TestEnd]" in prompt
    assert "[Q]:" in prompt
    assert "[A]:" in prompt


def test_parse_prep_steps_extracts_steps_correctly():
    from src.worker.tasks.interview_prep import _parse_prep_steps

    text = (
        "[PrepStepStart]:1:Learn Python\n"
        "Study Python basics and advanced topics.\n"
        "[PrepStepEnd]:1:Learn Python\n"
        "[PrepStepStart]:2:Practice Algorithms\n"
        "Work on algorithm problems.\n"
        "[PrepStepEnd]:2:Practice Algorithms\n"
    )
    steps = _parse_prep_steps(text)

    assert len(steps) == 2
    assert steps[0]["title"] == "Learn Python"
    assert steps[0]["step_number"] == 1
    assert "Python basics" in steps[0]["content"]
    assert steps[1]["title"] == "Practice Algorithms"


def test_parse_prep_steps_empty_text_returns_empty_list():
    from src.worker.tasks.interview_prep import _parse_prep_steps

    assert _parse_prep_steps("") == []


def test_parse_test_questions_extracts_questions_and_answers():
    from src.worker.tasks.interview_prep import _parse_test_questions

    text = (
        "[TestStart]\n"
        "[Q]:What is Python?\n"
        "[A]:A snake\n"
        "[A]:A programming language*\n"
        "[A]:A framework\n"
        "[A]:A database\n"
        "[TestEnd]\n"
    )
    questions = _parse_test_questions(text)

    assert len(questions) == 1
    assert "What is Python?" in questions[0]["question"]
    assert questions[0]["correct_index"] == 1
    assert len(questions[0]["options"]) == 4


def test_parse_test_questions_correct_index_from_star():
    from src.worker.tasks.interview_prep import _parse_test_questions

    text = (
        "[TestStart]\n"
        "[Q]:Which is correct?\n"
        "[A]:Wrong 1\n"
        "[A]:Wrong 2\n"
        "[A]:Correct answer*\n"
        "[A]:Wrong 3\n"
        "[TestEnd]\n"
    )
    questions = _parse_test_questions(text)

    assert questions[0]["correct_index"] == 2
    assert questions[0]["options"][2] == "Correct answer"


def test_parse_qa_blocks_extracts_answers():
    from src.worker.tasks.interview_qa import _parse_qa_blocks

    text = (
        "[QAStart]:best_achievement\n"
        "I successfully delivered a project on time.\n"
        "[QAEnd]:best_achievement\n"
    )
    result = _parse_qa_blocks(text)

    assert "best_achievement" in result
    assert "successfully delivered" in result["best_achievement"]


def test_parse_qa_blocks_empty_text():
    from src.worker.tasks.interview_qa import _parse_qa_blocks

    assert _parse_qa_blocks("") == {}
