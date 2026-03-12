"""Unit tests for the updated keyphrase prompt builder and keyphrase parser."""

import pytest

from src.services.ai.prompts import WorkExperienceEntry, build_per_company_key_phrases_prompt
from src.worker.tasks.work_experience import _parse_keyphrases_by_company


class TestBuildPerCompanyKeyPhrasesPrompt:
    def test_includes_resume_title(self):
        entries = [WorkExperienceEntry(company_name="Acme", stack="Python")]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Backend Developer",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "Backend Developer" in prompt

    def test_includes_skill_level_when_provided(self):
        entries = [WorkExperienceEntry(company_name="Acme", stack="Python")]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Developer",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
            skill_level="Senior",
        )
        assert "Senior" in prompt

    def test_skill_level_absent_by_default(self):
        entries = [WorkExperienceEntry(company_name="Acme", stack="Python")]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Developer",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "уровня" not in prompt

    def test_includes_achievements_in_experience_block(self):
        entries = [
            WorkExperienceEntry(
                company_name="TechCorp",
                stack="Python, Django",
                achievements="Сократил время запросов на 40%",
            )
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Backend Developer",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "TechCorp" in prompt
        assert "Сократил" in prompt

    def test_includes_duties_in_experience_block(self):
        entries = [
            WorkExperienceEntry(
                company_name="TechCorp",
                stack="React",
                duties="Разрабатывал интерфейсы",
            )
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Frontend Developer",
            main_keywords=["React"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "Разрабатывал" in prompt

    def test_includes_period_in_experience_block(self):
        entries = [
            WorkExperienceEntry(
                company_name="Corp",
                stack="Java",
                period="2020-2023",
            )
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Java Dev",
            main_keywords=["Java"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "2020-2023" in prompt

    def test_multiple_companies_all_included(self):
        entries = [
            WorkExperienceEntry(company_name="Alpha", stack="Go"),
            WorkExperienceEntry(company_name="Beta", stack="Rust"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Systems Developer",
            main_keywords=["Go", "Rust"],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "Alpha" in prompt
        assert "Beta" in prompt

    def test_format_section_present(self):
        entries = [WorkExperienceEntry(company_name="X", stack="Python")]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="formal",
            per_company_count=3,
            language="ru",
            work_experiences=entries,
        )
        assert "ФОРМАТ ВЫВОДА" in prompt
        assert "Компания:" in prompt


class TestParseKeyphrasesByCompany:
    def test_parses_single_company_block(self):
        raw = "Компания: TechCorp\n- фраза 1\n- фраза 2"
        result = _parse_keyphrases_by_company(raw)
        assert "TechCorp" in result
        assert "фраза 1" in result["TechCorp"]

    def test_parses_multiple_company_blocks(self):
        raw = "Компания: Alpha\n- phrase A\n- phrase B\n\nКомпания: Beta\n- phrase C\n- phrase D"
        result = _parse_keyphrases_by_company(raw)
        assert "Alpha" in result
        assert "Beta" in result
        assert "phrase A" in result["Alpha"]
        assert "phrase C" in result["Beta"]

    def test_returns_empty_dict_for_no_blocks(self):
        result = _parse_keyphrases_by_company("Just some text without company blocks")
        assert result == {}

    def test_ignores_empty_body(self):
        raw = "Компания: Empty\n"
        result = _parse_keyphrases_by_company(raw)
        assert "Empty" not in result

    @pytest.mark.parametrize(
        "company_name",
        ["Acme Corp", "ООО Технологии", "Google LLC"],
    )
    def test_parses_various_company_names(self, company_name: str):
        raw = f"Компания: {company_name}\n- some phrase"
        result = _parse_keyphrases_by_company(raw)
        assert company_name in result
