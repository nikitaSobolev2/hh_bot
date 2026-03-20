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

    def test_detailed_style_mentions_single_paragraph(self) -> None:
        prompt = build_cover_letter_system_prompt("detailed")
        assert "одного абзаца" in prompt or "абзац" in prompt.lower()

    def test_custom_style_uses_fallback(self) -> None:
        prompt = build_cover_letter_system_prompt("formal")
        assert "formal" in prompt or "Стиль:" in prompt

    def test_requires_single_paragraph_not_two(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "один абзац" in prompt.lower() or "одно связное" in prompt.lower()
        assert "2 абзаца" not in prompt

    def test_forbids_metrics_and_raw_numbers(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "процент" in prompt.lower()
        assert "ЗАПРЕТ НА МЕТРИКИ" in prompt or "метрик" in prompt.lower()

    def test_requires_verbatim_vacancy_title(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "дословно" in prompt.lower()
        assert "Должность" in prompt

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
        assert "Название вакансии для текста письма (дословно): Senior Python Developer" in content
        assert "Tech Corp" in content
        assert "Full description" in content

    def test_instructs_single_paragraph_no_metrics(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name="Corp",
            vacancy_description="Desc",
        )
        assert "один абзац" in content.lower()
        assert "процент" in content.lower() or "цифр" in content.lower()
        assert "дословно" in content.lower()

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
