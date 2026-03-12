"""Unit tests for vacancy summary (about-me) AI prompts."""


def test_build_vacancy_summary_system_prompt_contains_structure():
    from src.services.ai.prompts import build_vacancy_summary_system_prompt

    prompt = build_vacancy_summary_system_prompt()

    assert "О себе" in prompt
    assert "СТРУКТУРА" in prompt
    assert "ПРАВИЛА" in prompt


def test_build_vacancy_summary_user_content_includes_work_experiences():
    from src.services.ai.prompts import WorkExperienceEntry, build_vacancy_summary_user_content

    experiences = [
        WorkExperienceEntry(company_name="ACME", stack="Python"),
        WorkExperienceEntry(company_name="TechCorp", stack="Go"),
    ]
    content = build_vacancy_summary_user_content(
        work_experiences=experiences,
        tech_stack=["Python", "Go"],
        excluded_industries="gambling",
        location="Moscow",
        remote_preference="remote",
        additional_notes="Open to travel",
    )

    assert "ACME" in content
    assert "TechCorp" in content
    assert "gambling" in content
    assert "Moscow" in content
    assert "remote" in content


def test_build_vacancy_summary_user_content_without_optional_fields():
    from src.services.ai.prompts import WorkExperienceEntry, build_vacancy_summary_user_content

    experiences = [WorkExperienceEntry(company_name="Corp", stack="Java")]
    content = build_vacancy_summary_user_content(
        work_experiences=experiences,
        tech_stack=[],
        excluded_industries=None,
        location=None,
        remote_preference=None,
        additional_notes=None,
    )

    assert "Corp" in content


def test_build_standard_qa_system_prompt_format_markers_present():
    from src.services.ai.prompts import build_standard_qa_system_prompt

    prompt = build_standard_qa_system_prompt()

    assert "[QAStart]" in prompt
    assert "[QAEnd]" in prompt


def test_build_standard_qa_user_content_includes_questions():
    from src.services.ai.prompts import WorkExperienceEntry, build_standard_qa_user_content

    experiences = [WorkExperienceEntry(company_name="ACME", stack="Python")]
    content = build_standard_qa_user_content(
        work_experiences=experiences,
        question_keys=["best_achievement"],
        question_texts=["What are you proud of?"],
    )

    assert "best_achievement" in content
    assert "What are you proud of?" in content
    assert "ACME" in content
