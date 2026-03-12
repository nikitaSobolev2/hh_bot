"""Unit tests for the recommendation letter prompt builder."""

import pytest

from src.services.ai.prompts import REC_LETTER_CHARACTERS, build_recommendation_letter_prompt


class TestBuildRecommendationLetterPrompt:
    def test_includes_speaker_name(self):
        prompt = build_recommendation_letter_prompt(
            company_name="TechCorp",
            stack="Python",
            speaker_name="Иван Иванов",
            speaker_position=None,
            character_key="professionalism",
            language="ru",
        )
        assert "Иван Иванов" in prompt

    def test_includes_company_name(self):
        prompt = build_recommendation_letter_prompt(
            company_name="ООО Разработка",
            stack="Django",
            speaker_name="John Smith",
            speaker_position=None,
            character_key="teamwork",
            language="ru",
        )
        assert "ООО Разработка" in prompt

    def test_includes_speaker_position_when_provided(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Java",
            speaker_name="Alice",
            speaker_position="CTO",
            character_key="leadership",
            language="ru",
        )
        assert "CTO" in prompt

    def test_speaker_position_absent_when_none(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Java",
            speaker_name="Alice",
            speaker_position=None,
            character_key="leadership",
            language="ru",
        )
        assert ", None" not in prompt

    def test_includes_character_label_in_russian(self):
        prompt = build_recommendation_letter_prompt(
            company_name="X",
            stack="Python",
            speaker_name="A",
            speaker_position=None,
            character_key="leadership",
            language="ru",
        )
        assert "лидерство" in prompt.lower()

    def test_includes_character_label_in_english(self):
        prompt = build_recommendation_letter_prompt(
            company_name="X",
            stack="Python",
            speaker_name="A",
            speaker_position=None,
            character_key="leadership",
            language="en",
        )
        assert "leadership" in prompt.lower()

    def test_includes_achievements_when_provided(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Go",
            speaker_name="Bob",
            speaker_position=None,
            character_key="technical",
            language="ru",
            achievements="Оптимизировал систему кэширования",
        )
        assert "Оптимизировал" in prompt

    def test_includes_duties_when_provided(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Go",
            speaker_name="Bob",
            speaker_position=None,
            character_key="reliability",
            language="ru",
            duties="Разрабатывал микросервисы",
        )
        assert "Разрабатывал" in prompt

    def test_includes_focus_text_when_provided(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Python",
            speaker_name="Eve",
            speaker_position=None,
            character_key="initiative",
            language="ru",
            focus_text="Умение работать в команде",
        )
        assert "Умение работать в команде" in prompt

    def test_focus_text_absent_when_none(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Python",
            speaker_name="Eve",
            speaker_position=None,
            character_key="initiative",
            language="ru",
            focus_text=None,
        )
        assert "акцентируй" not in prompt

    def test_includes_period_in_role_info(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Python",
            speaker_name="Eve",
            speaker_position=None,
            character_key="reliability",
            language="ru",
            period="2021-2023",
        )
        assert "2021-2023" in prompt

    def test_includes_title_in_role_info(self):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Python",
            speaker_name="Eve",
            speaker_position=None,
            character_key="reliability",
            language="ru",
            title="Senior Developer",
        )
        assert "Senior Developer" in prompt

    def test_unknown_character_key_uses_key_as_fallback(self):
        prompt = build_recommendation_letter_prompt(
            company_name="X",
            stack="Python",
            speaker_name="A",
            speaker_position=None,
            character_key="unknown_key",
            language="ru",
        )
        assert "unknown_key" in prompt

    @pytest.mark.parametrize("character_key", list(REC_LETTER_CHARACTERS.keys()))
    def test_all_character_keys_are_valid(self, character_key: str):
        prompt = build_recommendation_letter_prompt(
            company_name="Corp",
            stack="Python",
            speaker_name="Test",
            speaker_position=None,
            character_key=character_key,
            language="ru",
        )
        assert len(prompt) > 100
