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
        assert "деловой" in prompt.lower()

    def test_friendly_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("friendly")
        assert "дружелюбный" in prompt.lower()

    def test_concise_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("concise")
        assert "краткий" in prompt.lower()

    def test_detailed_style_includes_style_guidance(self) -> None:
        prompt = build_cover_letter_system_prompt("detailed")
        assert "подробный" in prompt.lower()

    def test_custom_style_uses_fallback(self) -> None:
        prompt = build_cover_letter_system_prompt("formal")
        assert "formal" in prompt or "Стиль:" in prompt

    def test_includes_structure_section(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "СТРУКТУРА" in prompt
        assert "Обращение" in prompt

    def test_includes_anti_injection(self) -> None:
        prompt = build_cover_letter_system_prompt("professional")
        assert "БЕЗОПАСНОСТЬ" in prompt


class TestBuildCoverLetterUserContent:
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

    def test_empty_vacancy_description_uses_placeholder(self) -> None:
        content = build_cover_letter_user_content(
            work_experiences=[],
            vacancy_title="Dev",
            company_name=None,
            vacancy_description="",
        )
        assert "Должность:" in content
        assert "—" in content
