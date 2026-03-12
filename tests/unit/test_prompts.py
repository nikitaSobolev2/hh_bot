"""Unit tests for AI prompt builders."""

from src.services.ai.prompts import (
    WorkExperienceEntry,
    build_key_phrases_prompt,
    build_per_company_key_phrases_prompt,
)


class TestBuildKeyPhrasesPrompt:
    def test_includes_resume_title(self):
        prompt = build_key_phrases_prompt(
            resume_title="Backend Developer",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="формальный",
            count=5,
            language="ru",
        )
        assert "Backend Developer" in prompt

    def test_includes_main_keywords(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=["Python", "Django"],
            secondary_keywords=[],
            style="формальный",
            count=5,
            language="ru",
        )
        assert "Python" in prompt
        assert "Django" in prompt

    def test_includes_secondary_keywords(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=["Redis", "Docker"],
            style="формальный",
            count=5,
            language="ru",
        )
        assert "Redis" in prompt
        assert "Docker" in prompt

    def test_count_zero_uses_up_to_30(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="формальный",
            count=0,
            language="ru",
        )
        assert "не более чем из 30" in prompt

    def test_positive_count_exact(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=["Python"],
            secondary_keywords=[],
            style="формальный",
            count=7,
            language="ru",
        )
        assert "ровно 7" in prompt

    def test_includes_style_and_language(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="деловой",
            count=5,
            language="en",
        )
        assert "деловой" in prompt
        assert "en" in prompt

    def test_includes_quality_rules(self):
        prompt = build_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="формальный",
            count=5,
            language="ru",
        )
        assert "ТРЕБОВАНИЯ К КАЧЕСТВУ" in prompt
        assert "ФОРМАТ" in prompt


class TestBuildPerCompanyKeyPhrasesPrompt:
    def test_includes_all_companies(self):
        experiences = [
            WorkExperienceEntry(company_name="Acme Corp", stack="Python, Django"),
            WorkExperienceEntry(company_name="BigCo", stack="React, TypeScript"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Fullstack Developer",
            main_keywords=["Python", "React"],
            secondary_keywords=["Docker"],
            style="формальный",
            per_company_count=3,
            language="ru",
            work_experiences=experiences,
        )
        assert "Acme Corp" in prompt
        assert "BigCo" in prompt
        assert "Python, Django" in prompt
        assert "React, TypeScript" in prompt

    def test_includes_per_company_count(self):
        experiences = [
            WorkExperienceEntry(company_name="Co", stack="Go"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="формальный",
            per_company_count=5,
            language="ru",
            work_experiences=experiences,
        )
        assert "5" in prompt

    def test_includes_work_experience_section(self):
        experiences = [
            WorkExperienceEntry(company_name="TestCo", stack="Java"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="формальный",
            per_company_count=2,
            language="en",
            work_experiences=experiences,
        )
        assert "ОПЫТ РАБОТЫ КАНДИДАТА" in prompt

    def test_includes_quality_and_format_rules(self):
        experiences = [
            WorkExperienceEntry(company_name="Co", stack="Rust"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="Dev",
            main_keywords=[],
            secondary_keywords=[],
            style="формальный",
            per_company_count=2,
            language="ru",
            work_experiences=experiences,
        )
        assert "ТРЕБОВАНИЯ К КАЧЕСТВУ" in prompt
        assert "ФОРМАТ" in prompt

    def test_includes_resume_title_and_keywords(self):
        experiences = [
            WorkExperienceEntry(company_name="Co", stack="Python"),
        ]
        prompt = build_per_company_key_phrases_prompt(
            resume_title="ML Engineer",
            main_keywords=["PyTorch", "TensorFlow"],
            secondary_keywords=["Docker"],
            style="экспертный",
            per_company_count=4,
            language="ru",
            work_experiences=experiences,
        )
        assert "ML Engineer" in prompt
        assert "PyTorch" in prompt
        assert "TensorFlow" in prompt
        assert "Docker" in prompt
