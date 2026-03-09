"""Unit tests for vacancy analysis parsing and prompt builders."""

import pytest

from src.services.ai.client import VacancyAnalysis, _parse_vacancy_analysis
from src.services.ai.prompts import (
    build_vacancy_analysis_system_prompt,
    build_vacancy_analysis_user_content,
)

# ── _parse_vacancy_analysis ──────────────────────────────────────────


def test_parse_vacancy_analysis_extracts_all_three_blocks():
    raw = (
        "Плюсы: стек хорошо совпадает. Минусы: требуют знание AWS.\n\n"
        "[Stack]:Python,FastAPI,PostgreSQL,Docker\n"
        "[Compatibility]:78"
    )

    result = _parse_vacancy_analysis(raw)

    assert isinstance(result, VacancyAnalysis)
    assert "Плюсы" in result.summary
    assert "Python" in result.stack
    assert "FastAPI" in result.stack
    assert "PostgreSQL" in result.stack
    assert "Docker" in result.stack
    assert result.compatibility_score == 78.0


def test_parse_vacancy_analysis_summary_does_not_include_stack_line():
    raw = "Хорошее совпадение по фронтенду.\n\n[Stack]:React,TypeScript\n[Compatibility]:65"

    result = _parse_vacancy_analysis(raw)

    assert "[Stack]" not in result.summary
    assert "[Compatibility]" not in result.summary


def test_parse_vacancy_analysis_clamps_compatibility_to_100():
    raw = "Анализ.\n[Stack]:Go\n[Compatibility]:150"

    result = _parse_vacancy_analysis(raw)

    assert result.compatibility_score == 100.0


def test_parse_vacancy_analysis_returns_zero_compat_when_no_compatibility_line():
    raw = "Анализ без числа совместимости.\n[Stack]:Java,Spring"

    result = _parse_vacancy_analysis(raw)

    assert result.compatibility_score == 0.0


def test_parse_vacancy_analysis_returns_empty_stack_when_no_stack_line():
    raw = "Только анализ, без блока стека.\n[Compatibility]:50"

    result = _parse_vacancy_analysis(raw)

    assert result.stack == []


def test_parse_vacancy_analysis_summary_excludes_compatibility_line_when_no_stack_line():
    raw = "Хороший кандидат, стек не указан явно.\n[Compatibility]:78"

    result = _parse_vacancy_analysis(raw)

    assert "[Compatibility]" not in result.summary
    assert "78" not in result.summary
    assert result.compatibility_score == 78.0


def test_parse_vacancy_analysis_returns_full_text_as_summary_when_no_stack_line():
    raw = "Просто текст без форматирования."

    result = _parse_vacancy_analysis(raw)

    assert result.summary == raw.strip()
    assert result.stack == []
    assert result.compatibility_score == 0.0


def test_parse_vacancy_analysis_handles_empty_string():
    result = _parse_vacancy_analysis("")

    assert result.summary == ""
    assert result.stack == []
    assert result.compatibility_score == 0.0


def test_parse_vacancy_analysis_trims_whitespace_from_stack_items():
    raw = "Анализ.\n[Stack]: Python , FastAPI , Docker \n[Compatibility]:70"

    result = _parse_vacancy_analysis(raw)

    assert result.stack == ["Python", "FastAPI", "Docker"]


@pytest.mark.parametrize(
    ("raw", "expected_compat"),
    [
        ("A\n[Stack]:X\n[Compatibility]:0", 0.0),
        ("A\n[Stack]:X\n[Compatibility]:100", 100.0),
        ("A\n[Stack]:X\n[Compatibility]:55", 55.0),
    ],
)
def test_parse_vacancy_analysis_compat_boundary_values(raw, expected_compat):
    result = _parse_vacancy_analysis(raw)

    assert result.compatibility_score == expected_compat


# ── build_vacancy_analysis_system_prompt ────────────────────────────


def test_build_vacancy_analysis_system_prompt_includes_candidate_stack():
    prompt = build_vacancy_analysis_system_prompt(
        user_tech_stack=["Python", "Django"],
        user_work_experience="3 года backend-разработки",
    )

    assert "Python" in prompt
    assert "Django" in prompt
    assert "3 года backend-разработки" in prompt


def test_build_vacancy_analysis_system_prompt_includes_output_format_markers():
    prompt = build_vacancy_analysis_system_prompt(
        user_tech_stack=["Java"],
        user_work_experience="",
    )

    assert "[Stack]" in prompt
    assert "[Compatibility]" in prompt


def test_build_vacancy_analysis_system_prompt_handles_empty_stack_and_experience():
    prompt = build_vacancy_analysis_system_prompt(
        user_tech_stack=[],
        user_work_experience="",
    )

    assert "[Stack]" in prompt
    assert "[Compatibility]" in prompt
    assert "не указан" in prompt


# ── build_vacancy_analysis_user_content ─────────────────────────────


def test_build_vacancy_analysis_user_content_includes_title_and_skills():
    content = build_vacancy_analysis_user_content(
        vacancy_title="Senior Python Developer",
        vacancy_skills=["Python", "FastAPI", "PostgreSQL"],
        vacancy_description="Full description here.",
    )

    assert "Senior Python Developer" in content
    assert "Python" in content
    assert "FastAPI" in content
    assert "PostgreSQL" in content


def test_build_vacancy_analysis_user_content_passes_full_description_untruncated():
    long_description = "x" * 10000

    content = build_vacancy_analysis_user_content(
        vacancy_title="Dev",
        vacancy_skills=[],
        vacancy_description=long_description,
    )

    assert long_description in content
