"""Unit tests for cover letter prompt builders."""

from __future__ import annotations

from src.services.ai.prompts import (
    WorkExperienceEntry,
    build_cover_letter_system_prompt,
    build_cover_letter_user_content,
)


class TestBuildCoverLetterSystemPrompt:
    def test_professional_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "профессиональный" in prompt.lower()

    def test_friendly_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("friendly")
        assert "дружелюбный" in prompt.lower()

    def test_concise_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("concise")
        assert "лаконичный" in prompt.lower()

    def test_detailed_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("detailed")
        assert "подробнее" in prompt.lower() or "достижения" in prompt.lower()

    def test_custom_style_uses_fallback(self) -> None:
        prompt = build_cover_letter_system_prompt("formal")
        assert "formal" in prompt or "Стиль:" in prompt

    def test_includes_two_paragraph_structure(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "2 абзаца" in prompt or "два абзаца" in prompt
        assert "100" in prompt or "150" in prompt

    def test_includes_stack_mapping_and_company_relevance_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "В вашем стеке" in prompt or "сопоставь стек" in prompt
        assert "релевантно" in prompt or "компании" in prompt

    def test_forbids_formal_greeting_and_closing(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "Уважаемая команда" in prompt or "С уважением" in prompt
        assert "ЗАПРЕЩЕНО" in prompt

    def test_includes_anti_injection(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "БЕЗОПАСНОСТЬ" in prompt


class TestBuildCoverLetterUserContent:
    def test_includes_user_name(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
            user_name="Иван Петров",
        )
        assert "[ИМЯ КАНДИДАТА]" in content
        assert "Иван Петров" in content

    def test_user_name_defaults_to_kandidat(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
        )
        assert "Кандидат" in content

    def test_includes_work_experience(self) -> None:
        experiences = [
            WorkExperienceEntry(
                company_name="Acme",
                stack="Python",
                title="Developer",
                period="2020-2023",
                achievements="Achieved X",
                duties="Duties Y",
            )
        ]
        content = build_cover_letter_user_content(
            work_experiences=experiences,
            vacancy_title="Backend Dev",
            company_name="Acme Corp",
            vacancy_description="We need a Python dev.",
        )
        assert "Acme" in content
        assert "Python" in content
        assert "Achieved X" in content
        assert "Duties Y" in content

    def test_includes_vacancy_data(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Senior Python Developer",
            company_name="Tech Corp",
            vacancy_description="Full description of the vacancy.",
        )
        assert "Senior Python Developer" in content
        assert "Tech Corp" in content
        assert "Full description" in content

    def test_instructs_two_paragraphs_no_greeting(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
        )
        assert "2 абзаца" in content or "100" in content
        assert "Без обращения" in content or "без обращения" in content

    def test_includes_about_me_when_provided(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
            about_me="Fullstack-разработчик с 5 годами опыта.",
        )
        assert "[НЕСКОЛЬКО СЛОВ О СЕБЕ]" in content
        assert "Fullstack-разработчик" in content

    def test_omits_about_me_block_when_empty(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
            about_me="",
        )
        assert "[НЕСКОЛЬКО СЛОВ О СЕБЕ]" not in content

    def test_empty_vacancy_description_uses_placeholder(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name=None,
            vacancy_description="",
        )
        assert "Должность:" in content
        assert "—" in content
