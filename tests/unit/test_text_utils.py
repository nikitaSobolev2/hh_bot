"""Unit tests for text_utils module."""

from src.services.telegram.text_utils import parse_deep_learning_response


def test_parse_deep_learning_response_extracts_summary_and_plan():
    text = (
        "<Summary>\n"
        "Краткое введение:\n"
        "1. Пункт один\n"
        "2. Пункт два\n"
        "</Summary>\n\n"
        "<Plan>\n"
        "# Полный материал\n"
        "Детальное содержание..."
        "</Plan>"
    )
    summary, plan = parse_deep_learning_response(text)

    assert summary is not None
    assert "1. Пункт один" in summary
    assert "2. Пункт два" in summary
    assert plan is not None
    assert "# Полный материал" in plan
    assert "Детальное содержание" in plan


def test_parse_deep_learning_response_returns_none_when_tags_missing():
    text = "Plain text without tags"
    summary, plan = parse_deep_learning_response(text)

    assert summary is None
    assert plan is None


def test_parse_deep_learning_response_returns_none_for_empty_text():
    summary, plan = parse_deep_learning_response("")
    assert summary is None
    assert plan is None

    summary, plan = parse_deep_learning_response("   ")
    assert summary is None
    assert plan is None


def test_parse_deep_learning_response_handles_case_insensitive_tags():
    text = "<summary>Short</summary>\n\n<plan>Full content</plan>"
    summary, plan = parse_deep_learning_response(text)

    assert summary == "Short"
    assert plan == "Full content"


def test_parse_deep_learning_response_extracts_only_summary_when_plan_missing():
    text = "<Summary>\nIntro points\n</Summary>\n\nNo plan block"
    summary, plan = parse_deep_learning_response(text)

    assert summary == "Intro points"
    assert plan is None


def test_parse_deep_learning_response_extracts_only_plan_when_summary_missing():
    text = "No summary\n\n<Plan>\nFull material here\n</Plan>"
    summary, plan = parse_deep_learning_response(text)

    assert summary is None
    assert plan == "Full material here"
