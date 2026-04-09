from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.autoparse.services import (
    create_autoparse_company,
    generate_full_md,
    generate_links_txt,
    generate_summary_txt,
    get_reacted_vacancy_ids_for_user,
    reset_company_vacancy_pool,
)
from src.models.autoparse import AutoparsedVacancy


def _make_vacancy(**kwargs) -> AutoparsedVacancy:
    defaults = {
        "autoparse_company_id": 1,
        "hh_vacancy_id": "111",
        "url": "https://hh.ru/vacancy/111",
        "title": "Python Developer",
        "description": "Great job",
        "company_name": "Yandex",
        "company_url": "https://hh.ru/employer/1",
        "salary": "300 000 RUB",
        "work_experience": "3-6 years",
        "work_formats": "Remote",
        "employment_type": "Full-time",
        "work_schedule": "5/2",
        "tags": ["Python", "Django"],
        "compatibility_score": 85.0,
    }
    defaults.update(kwargs)
    return AutoparsedVacancy(**defaults)


class TestGenerateLinks:
    def test_single_vacancy(self):
        v = _make_vacancy()
        result = generate_links_txt([v])
        assert "https://hh.ru/vacancy/111" in result

    def test_multiple(self):
        v1 = _make_vacancy(hh_vacancy_id="1", url="https://hh.ru/vacancy/1")
        v2 = _make_vacancy(hh_vacancy_id="2", url="https://hh.ru/vacancy/2")
        result = generate_links_txt([v1, v2])
        assert result.count("\n") == 1


class TestGenerateSummary:
    def test_includes_header(self):
        v = _make_vacancy()
        result = generate_summary_txt([v])
        assert "Title | Company" in result

    def test_compatibility_shown(self):
        v = _make_vacancy(compatibility_score=72.0)
        result = generate_summary_txt([v])
        assert "72%" in result

    def test_no_compatibility(self):
        v = _make_vacancy(compatibility_score=None)
        result = generate_summary_txt([v])
        assert "N/A" in result


class TestGenerateFullMd:
    def test_markdown_format(self):
        v = _make_vacancy()
        result = generate_full_md([v])
        assert "# Python Developer" in result
        assert "**Salary**: 300 000 RUB" in result
        assert "85%" in result

    def test_no_compat_shows_na(self):
        v = _make_vacancy(compatibility_score=None)
        result = generate_full_md([v])
        assert "N/A" in result

    def test_no_company_url(self):
        v = _make_vacancy(company_url=None)
        result = generate_full_md([v])
        assert "Yandex" in result


class TestCreateAutoparseCompany:
    @pytest.mark.asyncio
    @patch("src.bot.modules.autoparse.services.AutoparseCompanyRepository")
    async def test_passes_include_reacted_in_feed_to_repo(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_company = MagicMock()
        mock_company.id = 1
        mock_repo.create = AsyncMock(return_value=mock_company)
        mock_repo_cls.return_value = mock_repo

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        await create_autoparse_company(
            mock_session,
            user_id=1,
            title="Python Dev",
            url="https://hh.ru/search?text=python",
            keywords="python",
            skills="Python,Django",
            include_reacted_in_feed=True,
        )

        mock_repo.create.assert_called_once()
        call_kwargs = mock_repo.create.call_args.kwargs
        assert call_kwargs["include_reacted_in_feed"] is True

    @pytest.mark.asyncio
    async def test_create_autoparse_company_default_include_reacted_is_false(self):
        mock_repo = MagicMock()
        mock_company = MagicMock()
        mock_company.id = 1
        mock_repo.create = AsyncMock(return_value=mock_company)

        with patch(
            "src.bot.modules.autoparse.services.AutoparseCompanyRepository",
            return_value=mock_repo,
        ):
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            await create_autoparse_company(
                mock_session,
                user_id=1,
                title="Dev",
                url="https://hh.ru/search",
                keywords="",
                skills="",
            )

            call_kwargs = mock_repo.create.call_args.kwargs
            assert call_kwargs.get("include_reacted_in_feed", False) is False


class TestGetReactedVacancyIdsForUser:
    @pytest.mark.asyncio
    async def test_returns_union_of_liked_and_disliked(self):
        mock_feed_repo = MagicMock()
        mock_feed_repo.get_all_liked_vacancy_ids_for_user = AsyncMock(
            return_value={1, 2, 3}
        )
        mock_feed_repo.get_all_disliked_vacancy_ids_for_user = AsyncMock(
            return_value={2, 4, 5}
        )
        mock_session = MagicMock()

        with patch(
            "src.bot.modules.autoparse.services.VacancyFeedSessionRepository",
            return_value=mock_feed_repo,
        ):
            result = await get_reacted_vacancy_ids_for_user(mock_session, user_id=42)

        assert result == {1, 2, 3, 4, 5}


class TestResetCompanyVacancyPool:
    @pytest.mark.asyncio
    async def test_clears_company_vacancies_and_feed_sessions(self):
        company = MagicMock()
        company.id = 7

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock(return_value=company)

        vacancy_repo = MagicMock()
        vacancy_repo.delete_all_by_company = AsyncMock()

        feed_repo = MagicMock()
        feed_repo.delete_all_for_company = AsyncMock()

        session = MagicMock()
        session.commit = AsyncMock()

        with (
            patch(
                "src.bot.modules.autoparse.services.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.bot.modules.autoparse.services.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.bot.modules.autoparse.services.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
        ):
            result = await reset_company_vacancy_pool(session, company_id=7)

        assert result is company
        feed_repo.delete_all_for_company.assert_awaited_once_with(7)
        vacancy_repo.delete_all_by_company.assert_awaited_once_with(7)
        company_repo.update.assert_awaited_once_with(company, last_delivered_at=None)
        session.commit.assert_awaited_once()
