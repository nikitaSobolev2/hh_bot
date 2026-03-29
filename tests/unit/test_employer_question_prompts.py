"""Tests for employer question answer prompt builders."""

from src.services.ai.prompts import (
    WorkExperienceEntry,
    build_employer_question_answer_user_content,
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
