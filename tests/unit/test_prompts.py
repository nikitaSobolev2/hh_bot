"""Unit tests for AI prompt builders."""

from src.services.ai.prompts import (
    AchievementExperienceEntry,
    VacancyCompatInput,
    WorkExperienceEntry,
    build_achievement_generation_prompt,
    build_achievement_generation_system_prompt,
    build_batch_compatibility_user_content,
    build_batch_keyword_extraction_system_prompt,
    build_batch_keyword_extraction_user_content,
    build_key_phrases_prompt,
    build_per_company_key_phrases_prompt,
    build_work_experience_achievements_prompt,
    build_work_experience_achievements_system_prompt,
    build_work_experience_duties_prompt,
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
        assert "ТРЕБОВАНИЯ К КЛЮЧЕВЫМ ФРАЗАМ" in prompt
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
        assert "ТРЕБОВАНИЯ К КЛЮЧЕВЫМ ФРАЗАМ" in prompt
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


class TestBuildBatchCompatibilityUserContent:
    def test_includes_all_vacancy_ids_and_titles(self):
        vacancies = [
            VacancyCompatInput("v1", "Python Dev", ["Python"], "desc1"),
            VacancyCompatInput("v2", "Java Dev", ["Java"], "desc2"),
        ]
        content = build_batch_compatibility_user_content(
            vacancies,
            user_tech_stack=["Python"],
            user_work_experience="3 years",
        )
        assert "v1" in content
        assert "v2" in content
        assert "Python Dev" in content
        assert "Java Dev" in content

    def test_includes_user_profile(self):
        vacancies = [
            VacancyCompatInput("v1", "Dev", [], "desc"),
        ]
        content = build_batch_compatibility_user_content(
            vacancies,
            user_tech_stack=["Python", "Django"],
            user_work_experience="5 years backend",
        )
        assert "Python, Django" in content
        assert "5 years backend" in content

    def test_preserves_vacancy_order(self):
        vacancies = [
            VacancyCompatInput("a", "A", [], "d1"),
            VacancyCompatInput("b", "B", [], "d2"),
        ]
        content = build_batch_compatibility_user_content(
            vacancies, user_tech_stack=[], user_work_experience=""
        )
        pos_a = content.index("[Вакансия a]")
        pos_b = content.index("[Вакансия b]")
        assert pos_a < pos_b


class TestBuildBatchKeywordExtractionPrompt:
    def test_batch_keyword_system_prompt_contains_format_markers(self):
        prompt = build_batch_keyword_extraction_system_prompt()
        assert "[Vacancy]:" in prompt
        assert "[Keywords]:" in prompt
        assert "[VacancyEnd]:" in prompt

    def test_batch_keyword_system_prompt_contains_good_example(self):
        prompt = build_batch_keyword_extraction_system_prompt()
        assert "12345" in prompt
        assert "Python, FastAPI, PostgreSQL" in prompt or "FastAPI" in prompt

    def test_batch_keyword_system_prompt_contains_bad_examples(self):
        prompt = build_batch_keyword_extraction_system_prompt()
        assert "знание Python" in prompt or "не каноничная" in prompt
        assert "коммуникабельность" in prompt or "soft" in prompt.lower()

    def test_batch_keyword_user_content_includes_all_vacancies(self):
        vacancies = [
            VacancyCompatInput("a1", "Python Dev", ["Python"], "desc1"),
            VacancyCompatInput("b2", "Java Dev", ["Java"], "desc2"),
        ]
        content = build_batch_keyword_extraction_user_content(vacancies)
        assert "a1" in content
        assert "b2" in content
        assert "Python Dev" in content
        assert "Java Dev" in content

    def test_batch_keyword_user_content_truncates_description(self):
        long_desc = "x" * 5000
        vacancies = [
            VacancyCompatInput("v1", "Dev", [], long_desc),
        ]
        content = build_batch_keyword_extraction_user_content(vacancies)
        assert len(content) < len(long_desc) + 500
        assert "x" * 3000 in content
        assert "x" * 3001 not in content


class TestAchievementPrompts:
    """Tests for achievement generation prompts (aligned with keyphrases rules)."""

    def test_achievement_generation_system_prompt_contains_quality_rules(self):
        prompt = build_achievement_generation_system_prompt()
        assert "ТРЕБОВАНИЯ К ДОСТИЖЕНИЯМ" in prompt
        assert "результат" in prompt
        assert "бизнес-эффект" in prompt

    def test_achievement_generation_system_prompt_contains_shared_examples(self):
        prompt = build_achievement_generation_system_prompt()
        assert "ПРИМЕРЫ" in prompt
        assert "Перевел сервис биллинга" in prompt
        assert "300%" in prompt
        assert "Улучшил процессы" in prompt or "Повысил эффективность" in prompt

    def test_achievement_generation_system_prompt_contains_format_markers(self):
        prompt = build_achievement_generation_system_prompt()
        assert "[AchStart]" in prompt
        assert "[AchEnd]" in prompt

    def test_work_experience_achievements_system_prompt_contains_quality_rules(self):
        prompt = build_work_experience_achievements_system_prompt()
        assert "ТРЕБОВАНИЯ К ДОСТИЖЕНИЯМ" in prompt

    def test_work_experience_achievements_system_prompt_contains_shared_examples(self):
        prompt = build_work_experience_achievements_system_prompt()
        assert "ПРИМЕРЫ" in prompt
        assert "Перевел сервис биллинга" in prompt
        assert "300%" in prompt

    def test_achievement_generation_prompt_includes_company_data(self):
        entries = [
            AchievementExperienceEntry(
                company_name="Acme",
                stack="Python, Django",
                user_achievements="Built API",
                user_responsibilities=None,
            ),
        ]
        prompt = build_achievement_generation_prompt(entries)
        assert "Acme" in prompt
        assert "Python, Django" in prompt
        assert "Built API" in prompt


class TestWorkExperiencePromptsReferenceText:
    """Reference-based WE achievements/duties user prompts."""

    def test_achievements_prompt_without_reference_unchanged_shape(self):
        p = build_work_experience_achievements_prompt(
            "Acme", "Python", title="Dev", period="2020"
        )
        assert "<reference_text>" not in p
        assert "Acme" in p
        assert "[ОПОРНЫЙ ТЕКСТ]" not in p

    def test_achievements_prompt_wraps_reference_text(self):
        p = build_work_experience_achievements_prompt(
            "Acme",
            "Python",
            title="Dev",
            period="2020",
            reference_text="Shipped billing v2 with Kafka.",
        )
        assert "<reference_text>" in p
        assert "</reference_text>" in p
        assert "Shipped billing v2 with Kafka." in p
        assert "[ОПОРНЫЙ ТЕКСТ]" in p

    def test_duties_prompt_wraps_reference_text(self):
        p = build_work_experience_duties_prompt(
            "Acme",
            "Go",
            reference_text="Maintained CI pipelines.",
        )
        assert "<reference_text>" in p
        assert "Maintained CI pipelines." in p
        assert "[ОПОРНЫЙ ТЕКСТ]" in p

    def test_achievements_prompt_includes_db_snapshot_with_reference(self):
        p = build_work_experience_achievements_prompt(
            "Acme",
            "Python",
            reference_text="New notes.",
            existing_duties="- Разрабатывал API",
            existing_achievements="- Старый пункт",
        )
        assert "[ДАННЫЕ ЗАПИСИ ИЗ БД]" in p
        assert "<existing_duties>" in p
        assert "Разрабатывал API" in p
        assert "<existing_achievements>" in p
        assert "Старый пункт" in p
