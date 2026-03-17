"""Integration tests for autoparse bot handlers."""

from unittest.mock import MagicMock

from src.bot.modules.autoparse.callbacks import AutoparseCallback, AutoparseDownloadCallback
from src.bot.modules.autoparse.services import (
    format_company_detail,
    generate_links_txt,
)
from src.models.autoparse import AutoparseCompany, AutoparsedVacancy


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
        )
        text = format_company_detail(company, 42, i18n)
        assert "Python Dev" in text
        assert "42" in text

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
