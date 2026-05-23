"""Unit tests for integrate duties AI prompts."""


def test_build_integrate_duties_system_prompt_requires_json():
    from src.services.ai.prompts import build_integrate_duties_system_prompt

    prompt = build_integrate_duties_system_prompt()

    assert "work_experiences" in prompt
    assert "work_exp_id" in prompt
    assert "JSON" in prompt


def test_build_integrate_duties_user_content_contains_keywords_and_duties():
    from src.services.ai.prompts import WorkExperienceInput, build_integrate_duties_user_content

    keywords = [f"kw{i}" for i in range(25)]
    entries = [
        WorkExperienceInput(
            work_exp_id=10,
            company_name="Acme",
            stack="Python",
            duties="- Built APIs\n- Reviewed code",
        )
    ]

    content = build_integrate_duties_user_content("Python Developer", keywords, entries)

    assert "work_exp_id=10" in content
    assert "Acme" in content
    assert "Built APIs" in content
    assert "kw0" in content
    assert "TOP 25" in content
