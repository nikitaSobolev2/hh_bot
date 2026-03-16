"""Unit tests for interview AI prompt builders."""

import pytest

from src.services.ai.prompts import (
    build_company_review_prompt,
    build_improvement_flow_system_prompt,
    build_improvement_flow_user_content,
    build_interview_analysis_system_prompt,
    build_interview_analysis_user_content,
    build_questions_to_ask_prompt,
)


class TestBuildInterviewAnalysisSystemPrompt:
    def test_contains_output_format_markers(self):
        prompt = build_interview_analysis_system_prompt()
        assert "[InterviewSummaryStart]" in prompt
        assert "[InterviewSummaryEnd]" in prompt
        assert "[ImproveStart]" in prompt
        assert "[ImproveEnd]" in prompt

    def test_mentions_analysis_task(self):
        prompt = build_interview_analysis_system_prompt()
        assert "собеседован" in prompt.lower() or "анализ" in prompt.lower()

    def test_mentions_vacancy_context(self):
        prompt = build_interview_analysis_system_prompt()
        assert "вакансии" in prompt or "вакансия" in prompt

    def test_mentions_output_format_rules(self):
        prompt = build_interview_analysis_system_prompt()
        assert "ФОРМАТ" in prompt


class TestBuildInterviewAnalysisUserContent:
    def test_includes_vacancy_title(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Backend Developer",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "Backend Developer" in content

    def test_includes_company_when_provided(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name="Acme Corp",
            experience_level=None,
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "Acme Corp" in content

    def test_omits_company_when_none(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "Компания:" not in content

    def test_includes_experience_level(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level="3-6 лет",
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "3-6 лет" in content

    def test_includes_questions_and_answers(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[
                {"question": "Что такое REST?", "answer": "Архитектурный стиль"},
            ],
            user_improvement_notes=None,
        )
        assert "Что такое REST?" in content
        assert "Архитектурный стиль" in content

    def test_includes_multiple_questions_numbered(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[
                {"question": "Q1", "answer": "A1"},
                {"question": "Q2", "answer": "A2"},
            ],
            user_improvement_notes=None,
        )
        assert "Вопрос 1" in content
        assert "Вопрос 2" in content

    def test_includes_user_notes_when_provided(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[],
            user_improvement_notes="Нужно улучшить знания SQL",
        )
        assert "Нужно улучшить знания SQL" in content
        assert "ЗАМЕТКИ" in content

    def test_omits_notes_section_when_none(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "ЗАМЕТКИ" not in content

    def test_includes_description_when_provided(self):
        content = build_interview_analysis_user_content(
            vacancy_title="Dev",
            vacancy_description="Описание вакансии с требованиями.",
            company_name=None,
            experience_level=None,
            questions_answers=[],
            user_improvement_notes=None,
        )
        assert "Описание вакансии с требованиями." in content


class TestBuildImprovementFlowSystemPrompt:
    def test_contains_step_guidance(self):
        prompt = build_improvement_flow_system_prompt()
        assert "шаг" in prompt.lower() or "план" in prompt.lower()

    def test_mentions_format_rules(self):
        prompt = build_improvement_flow_system_prompt()
        assert "ФОРМАТ" in prompt

    def test_is_non_empty_string(self):
        prompt = build_improvement_flow_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100


class TestBuildImprovementFlowUserContent:
    def test_includes_technology_title(self):
        content = build_improvement_flow_user_content(
            technology_title="React",
            improvement_summary="Не знает хуки и контекст.",
            vacancy_title="Frontend Dev",
            vacancy_description=None,
        )
        assert "React" in content

    def test_includes_improvement_summary(self):
        content = build_improvement_flow_user_content(
            technology_title="React",
            improvement_summary="Не знает хуки и контекст.",
            vacancy_title="Frontend Dev",
            vacancy_description=None,
        )
        assert "Не знает хуки и контекст." in content

    def test_includes_vacancy_title(self):
        content = build_improvement_flow_user_content(
            technology_title="React",
            improvement_summary="Проблемы с хуками.",
            vacancy_title="Frontend Developer",
            vacancy_description=None,
        )
        assert "Frontend Developer" in content

    def test_includes_description_when_provided(self):
        content = build_improvement_flow_user_content(
            technology_title="React",
            improvement_summary="Проблемы.",
            vacancy_title="Dev",
            vacancy_description="Требуется глубокое знание React 18.",
        )
        assert "Требуется глубокое знание React 18." in content

    def test_truncates_long_description(self):
        long_desc = "x" * 5000
        content = build_improvement_flow_user_content(
            technology_title="React",
            improvement_summary="Проблемы.",
            vacancy_title="Dev",
            vacancy_description=long_desc,
        )
        assert len(content) < len(long_desc) + 500

    @pytest.mark.parametrize("title", ["Python", "Docker", "SQL", "TypeScript"])
    def test_various_technology_titles(self, title: str):
        content = build_improvement_flow_user_content(
            technology_title=title,
            improvement_summary="Слабые знания.",
            vacancy_title="Dev",
            vacancy_description=None,
        )
        assert title in content


# ── Company review prompts ─────────────────────────────────────────────────────


class TestBuildCompanyReviewPrompt:
    def test_build_company_review_prompt_contains_company(self):
        content = build_company_review_prompt(
            vacancy_title="Backend Dev",
            vacancy_description=None,
            company_name="Acme Corp",
            experience_level=None,
        )
        assert "Acme Corp" in content
        assert "КОМПАНИЯ" in content

    def test_includes_vacancy_title(self):
        content = build_company_review_prompt(
            vacancy_title="Python Developer",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
        )
        assert "Python Developer" in content


# ── Questions to ask prompts ───────────────────────────────────────────────────


class TestBuildQuestionsToAskPrompt:
    def test_build_questions_to_ask_prompt_contains_vacancy(self):
        content = build_questions_to_ask_prompt(
            vacancy_title="Frontend Developer",
            vacancy_description=None,
            company_name=None,
            experience_level=None,
        )
        assert "Frontend Developer" in content
        assert "ВАКАНСИЯ" in content

    def test_includes_company_when_provided(self):
        content = build_questions_to_ask_prompt(
            vacancy_title="Dev",
            vacancy_description=None,
            company_name="TechCo",
            experience_level=None,
        )
        assert "TechCo" in content
