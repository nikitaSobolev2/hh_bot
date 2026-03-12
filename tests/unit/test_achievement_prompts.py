"""Unit tests for achievement generation AI prompts."""


def test_build_achievement_generation_prompt_contains_company_name():
    from src.services.ai.prompts import (
        AchievementExperienceEntry,
        build_achievement_generation_prompt,
    )

    entries = [
        AchievementExperienceEntry(
            company_name="ACME Corp",
            stack="Python, Django",
            user_achievements="Launched new product",
            user_responsibilities="Backend development",
        )
    ]
    prompt = build_achievement_generation_prompt(entries)

    assert "ACME Corp" in prompt
    assert "Python, Django" in prompt
    assert "Launched new product" in prompt
    assert "Backend development" in prompt


def test_build_achievement_generation_prompt_format_markers_present():
    from src.services.ai.prompts import (
        AchievementExperienceEntry,
        build_achievement_generation_prompt,
    )

    entries = [
        AchievementExperienceEntry(
            company_name="Tech Inc",
            stack="Go",
            user_achievements=None,
            user_responsibilities=None,
        )
    ]
    prompt = build_achievement_generation_prompt(entries)

    assert "[AchStart]" in prompt
    assert "[AchEnd]" in prompt


def test_build_achievement_generation_prompt_multiple_companies():
    from src.services.ai.prompts import (
        AchievementExperienceEntry,
        build_achievement_generation_prompt,
    )

    entries = [
        AchievementExperienceEntry("Company A", "Python", None, None),
        AchievementExperienceEntry("Company B", "Java", "Won award", "Lead team"),
    ]
    prompt = build_achievement_generation_prompt(entries)

    assert "Company A" in prompt
    assert "Company B" in prompt


def test_parse_achievement_blocks_extracts_company_blocks():
    from src.worker.tasks.achievements import _parse_achievement_blocks

    text = (
        "[AchStart]:ACME Corp\n"
        "- Improved performance by 40%\n"
        "- Built new API\n"
        "[AchEnd]:ACME Corp\n"
        "[AchStart]:Tech Inc\n"
        "- Led team of 5 developers\n"
        "[AchEnd]:Tech Inc\n"
    )
    result = _parse_achievement_blocks(text)

    assert "ACME Corp" in result
    assert "Tech Inc" in result
    assert "Improved performance" in result["ACME Corp"]
    assert "Led team" in result["Tech Inc"]


def test_parse_achievement_blocks_empty_text_returns_empty_dict():
    from src.worker.tasks.achievements import _parse_achievement_blocks

    assert _parse_achievement_blocks("") == {}


def test_parse_achievement_blocks_ignores_malformed_blocks():
    from src.worker.tasks.achievements import _parse_achievement_blocks

    text = "[AchStart]:Company\nsome text"
    result = _parse_achievement_blocks(text)
    assert "Company" not in result
