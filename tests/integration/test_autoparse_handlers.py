"""Integration tests for autoparse bot handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.autoparse.keyboards import confirm_rebuild_company_keyboard
from src.bot.modules.autoparse.callbacks import AutoparseCallback, AutoparseDownloadCallback
from src.bot.modules.autoparse.services import (
    format_company_detail,
    generate_links_txt,
)
from src.models.autoparse import AutoparseCompany, AutoparsedVacancy


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.is_admin = False
    user.language_code = "ru"
    return user


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.locale = "ru"
    i18n.get = MagicMock(side_effect=lambda key, **kw: key)
    return i18n


def _make_callback(callback_data) -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.data = callback_data.pack()
    callback.answer = AsyncMock()
    return callback


def _make_company(company_id: int = 1, user_id: int = 1) -> MagicMock:
    company = MagicMock()
    company.id = company_id
    company.user_id = user_id
    company.vacancy_title = "Python Dev"
    return company


class TestAutoparseCallbacks:
    def test_callback_packing(self):
        cb = AutoparseCallback(action="list", page=2)
        packed = cb.pack()
        assert "ap:" in packed

        parsed = AutoparseCallback.unpack(packed)
        assert parsed.action == "list"
        assert parsed.page == 2

    def test_download_callback(self):
        cb = AutoparseDownloadCallback(company_id=5, format="links_txt")
        packed = cb.pack()
        parsed = AutoparseDownloadCallback.unpack(packed)
        assert parsed.company_id == 5
        assert parsed.format == "links_txt"

    def test_update_compat_unseen_callback(self):
        cb = AutoparseCallback(action="update_compat_unseen")
        packed = cb.pack()
        parsed = AutoparseCallback.unpack(packed)
        assert parsed.action == "update_compat_unseen"

    def test_view_feed_below_compat_callback(self):
        cb = AutoparseCallback(action="view_feed_below_compat")
        packed = cb.pack()
        parsed = AutoparseCallback.unpack(packed)
        assert parsed.action == "view_feed_below_compat"

    def test_edit_search_url_callback(self):
        cb = AutoparseCallback(action="edit_search_url", company_id=7)
        packed = cb.pack()
        parsed = AutoparseCallback.unpack(packed)
        assert parsed.action == "edit_search_url"
        assert parsed.company_id == 7


class TestFormatCompanyDetail:
    def test_enabled_company(self):
        i18n = MagicMock()
        i18n.get = MagicMock(side_effect=lambda k, **kw: k)
        company = AutoparseCompany(
            id=1,
            user_id=1,
            vacancy_title="Python Dev",
            search_url="https://hh.ru/search?text=python",
            keyword_filter="python",
            skills="Python,Django",
            is_enabled=True,
            total_runs=5,
            last_parsed_at=None,
            parse_mode="web",
        )
        text = format_company_detail(company, 42, i18n)
        assert "Python Dev" in text
        assert "42" in text
        assert "autoparse-parse-mode-web-label" in text

    def test_disabled_company(self):
        i18n = MagicMock()
        i18n.get = MagicMock(side_effect=lambda k, **kw: k)
        company = AutoparseCompany(
            id=2,
            user_id=1,
            vacancy_title="Java Dev",
            search_url="https://hh.ru/search?text=java",
            is_enabled=False,
            total_runs=0,
        )
        text = format_company_detail(company, 0, i18n)
        assert "autoparse-status-disabled" in text


class TestDownloadGeneration:
    def test_links_txt(self):
        v = AutoparsedVacancy(
            autoparse_company_id=1,
            hh_vacancy_id="1",
            url="https://hh.ru/vacancy/1",
            title="Dev",
        )
        result = generate_links_txt([v])
        assert "https://hh.ru/vacancy/1" in result


class TestRebuildPoolHandlers:
    @pytest.mark.asyncio
    async def test_rebuild_pool_prompt_shows_confirmation(self, mock_session):
        from src.bot.modules.autoparse.handlers import rebuild_pool_prompt

        callback_data = AutoparseCallback(action="rebuild_pool_prompt", company_id=7)
        callback = _make_callback(callback_data)
        user = _make_user()
        i18n = _make_i18n()
        company = _make_company(company_id=7, user_id=user.id)

        with patch(
            "src.bot.modules.autoparse.handlers.ap_service.get_autoparse_detail",
            new=AsyncMock(return_value=company),
        ) as mock_get_detail:
            await rebuild_pool_prompt(callback, callback_data, user, mock_session, i18n)

        mock_get_detail.assert_awaited_once_with(mock_session, 7, user.id)
        callback.message.edit_text.assert_awaited_once_with(
            "autoparse-confirm-rebuild-pool",
            reply_markup=confirm_rebuild_company_keyboard(company.id, i18n),
        )
        callback.answer.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_confirm_rebuild_pool_resets_only_and_rerenders_detail(self, mock_session):
        from src.bot.modules.autoparse.handlers import confirm_rebuild_pool

        callback_data = AutoparseCallback(action="confirm_rebuild_pool", company_id=7)
        callback = _make_callback(callback_data)
        user = _make_user()
        i18n = _make_i18n()
        company = _make_company(company_id=7, user_id=user.id)

        with (
            patch(
                "src.bot.modules.autoparse.handlers.ap_service.get_autoparse_detail",
                new=AsyncMock(return_value=company),
            ) as mock_get_detail,
            patch(
                "src.bot.modules.autoparse.handlers.ap_service.reset_company_vacancy_pool",
                new=AsyncMock(return_value=company),
            ) as mock_reset,
            patch(
                "src.bot.modules.autoparse.handlers._render_company_detail_message",
                new=AsyncMock(),
            ) as mock_render_detail,
        ):
            await confirm_rebuild_pool(callback, callback_data, user, mock_session, i18n)

        mock_get_detail.assert_awaited_once_with(mock_session, 7, user.id)
        mock_reset.assert_awaited_once_with(mock_session, 7, user.id)
        mock_render_detail.assert_awaited_once_with(
            callback.message,
            user,
            mock_session,
            i18n,
            company,
        )
        callback.answer.assert_awaited_once_with(
            "autoparse-rebuild-pool-started",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_confirm_rebuild_pool_alerts_when_company_missing(self, mock_session):
        from src.bot.modules.autoparse.handlers import confirm_rebuild_pool

        callback_data = AutoparseCallback(action="confirm_rebuild_pool", company_id=7)
        callback = _make_callback(callback_data)
        user = _make_user()
        i18n = _make_i18n()

        with (
            patch(
                "src.bot.modules.autoparse.handlers.ap_service.get_autoparse_detail",
                new=AsyncMock(return_value=None),
            ) as mock_get_detail,
        ):
            await confirm_rebuild_pool(callback, callback_data, user, mock_session, i18n)

        mock_get_detail.assert_awaited_once_with(mock_session, 7, user.id)
        callback.message.edit_text.assert_not_called()
        callback.answer.assert_awaited_once_with("autoparse-not-found", show_alert=True)
