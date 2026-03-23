"""Unit tests for cover letter standalone flow (main menu)."""

from __future__ import annotations

from src.bot.modules.cover_letter.handlers import _parse_idempotency_key
from src.bot.modules.cover_letter.services import parse_hh_vacancy_id
from src.worker.tasks.cover_letter import _build_cover_letter_keyboard


class TestParseIdempotencyKey:
    def test_parses_new_format_returns_source_and_vacancy_id(self) -> None:
        result = _parse_idempotency_key("cover_letter:1:standalone:42")
        assert result == ("standalone", 42)

    def test_parses_autoparse_format_returns_autoparse_and_vacancy_id(self) -> None:
        result = _parse_idempotency_key("cover_letter:1:autoparse:10")
        assert result == ("autoparse", 10)

    def test_parses_legacy_format_returns_autoparse_and_vacancy_id(self) -> None:
        result = _parse_idempotency_key("cover_letter:1:42")
        assert result == ("autoparse", 42)

    def test_returns_none_for_invalid_format(self) -> None:
        assert _parse_idempotency_key("invalid") is None
        assert _parse_idempotency_key("cover_letter:1") is None
        assert _parse_idempotency_key("cover_letter:1:standalone:abc") is None


class TestParseHhVacancyId:
    def test_extracts_id_from_standard_url(self) -> None:
        assert parse_hh_vacancy_id("https://hh.ru/vacancy/12345678") == "12345678"

    def test_extracts_id_from_alternate_domain(self) -> None:
        assert parse_hh_vacancy_id("https://spb.hh.ru/vacancy/999") == "999"

    def test_returns_none_for_invalid_url(self) -> None:
        assert parse_hh_vacancy_id("https://example.com/vacancy/123") is None
        assert parse_hh_vacancy_id("not a url") is None
        assert parse_hh_vacancy_id("") is None


class TestBuildCoverLetterKeyboardStandalone:
    def test_returns_keyboard_with_regenerate_and_back_when_standalone(self) -> None:
        keyboard = _build_cover_letter_keyboard(
            session_id=0, vacancy_id=42, locale="ru", standalone=True
        )
        assert keyboard.inline_keyboard
        all_callback_datas = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        assert any("regenerate" in (d or "") for d in all_callback_datas)
        assert any("cl" in (d or "") and "list" in (d or "") for d in all_callback_datas)

    def test_standalone_keyboard_does_not_include_feed_actions(self) -> None:
        keyboard = _build_cover_letter_keyboard(
            session_id=0, vacancy_id=42, locale="ru", standalone=True
        )
        all_callback_datas = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        assert not any("like" in (d or "") for d in all_callback_datas)
        assert not any("back_to_vacancy" in (d or "") for d in all_callback_datas)
