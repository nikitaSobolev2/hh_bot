"""Tests for employer question answer prompt builders."""

from src.services.ai.prompts import (
    WorkExperienceEntry,
    build_employer_question_answer_user_content,
    strip_employer_answer_plain_text,
)


def test_build_employer_question_answer_user_content_includes_blocks():
    user_content = build_employer_question_answer_user_content(
        vacancy_title="Python Dev",
        vacancy_description="Need Django",
        company_name="ACME",
        experience_level="3-6",
        hh_vacancy_url="https://hh.ru/vacancy/1",
        employer_question="Why Django?",
        work_experiences=[
            WorkExperienceEntry(
                company_name="X",
                stack="Django",
                title="Dev",
                period="2020–2024",
                achievements="Shipped API",
                duties="Backend",
            )
        ],
        about_me="Backend focus",
    )
    assert "Python Dev" in user_content
    assert "ACME" in user_content
    assert "Need Django" in user_content
    assert "Why Django?" in user_content
    assert "Django" in user_content
    assert "Backend focus" in user_content
    assert "вопрос_работодателя" in user_content


def test_build_employer_question_answer_user_content_regenerate_adds_variant():
    user_content = build_employer_question_answer_user_content(
        vacancy_title="Python Dev",
        vacancy_description=None,
        company_name=None,
        experience_level=None,
        hh_vacancy_url=None,
        employer_question="Why?",
        work_experiences=[],
        regenerate=True,
        variation_nonce="abc123",
    )
    assert "abc123" in user_content
    assert "ИД_ВАРИАНТА" in user_content


def test_strip_employer_answer_plain_text_removes_markdown_and_tables():
    raw = (
        "**Ответ:**\n\n"
        "Line one.\n"
        "| A | B |\n"
        "|---|---|\n"
        "| x | y |\n"
        "More **bold** text."
    )
    out = strip_employer_answer_plain_text(raw)
    assert "|" not in out or "Line one" in out
    assert "Ответ:" in out
    assert "**" not in out
    assert "bold" in out
