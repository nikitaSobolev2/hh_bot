"""Unit tests for autoparse task helper functions."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.tasks.autoparse import (
    _INTER_MESSAGE_DELAY_SECONDS,
    _build_user_profile,
    _deliver_results_async,
    _format_vacancy_message,
    _resolve_cached_vacancy,
    _send_vacancies_individually,
)


class TestBuildUserProfile:
    def test_returns_custom_stack_when_set(self):
        ap_settings = {"tech_stack": ["Python", "Django"]}
        work_experiences = []

        stack, exp = _build_user_profile(ap_settings, work_experiences)

        assert stack == ["Python", "Django"]
        assert exp == ""

    def test_derives_stack_from_work_experiences_when_no_custom_stack(self):
        exp_entry = MagicMock()
        exp_entry.company_name = "Acme"
        exp_entry.stack = "Python, FastAPI"

        stack, exp = _build_user_profile({}, [exp_entry])

        assert "Python" in stack
        assert "FastAPI" in stack
        assert "Acme — Python, FastAPI" in exp

    def test_returns_empty_profile_when_no_data(self):
        stack, exp = _build_user_profile({}, [])

        assert stack == []
        assert exp == ""

    def test_formats_experience_from_multiple_entries(self):
        e1 = MagicMock()
        e1.company_name = "Alpha"
        e1.stack = "Go"
        e2 = MagicMock()
        e2.company_name = "Beta"
        e2.stack = "Rust"

        _, exp = _build_user_profile({}, [e1, e2])

        assert "Alpha — Go" in exp
        assert "Beta — Rust" in exp


class TestFormatVacancyMessage:
    def _make_vacancy(
        self,
        *,
        url: str = "https://hh.ru/vacancy/1",
        title: str = "Backend Dev",
        salary: str | None = None,
        compatibility_score: float | None = None,
        company_name: str | None = None,
        work_formats: str | None = None,
        work_experience: str | None = None,
        employment_type: str | None = None,
        work_schedule: str | None = None,
        working_hours: str | None = None,
        raw_skills: list | None = None,
    ):
        v = MagicMock()
        v.url = url
        v.title = title
        v.salary = salary
        v.compatibility_score = compatibility_score
        v.company_name = company_name
        v.work_formats = work_formats
        v.work_experience = work_experience
        v.employment_type = employment_type
        v.work_schedule = work_schedule
        v.working_hours = working_hours
        v.raw_skills = raw_skills
        return v

    def test_title_rendered_as_html_link(self):
        v = self._make_vacancy(title="Python Dev", url="https://hh.ru/vacancy/42")
        msg = _format_vacancy_message(v)
        assert "<a href='https://hh.ru/vacancy/42'>Python Dev</a>" in msg

    def test_includes_salary_when_present(self):
        v = self._make_vacancy(salary="от 150 000 ₽")
        msg = _format_vacancy_message(v)
        assert "от 150 000 ₽" in msg

    def test_omits_salary_when_absent(self):
        v = self._make_vacancy(salary=None)
        msg = _format_vacancy_message(v)
        assert "₽" not in msg

    def test_includes_compat_score_when_present(self):
        v = self._make_vacancy(compatibility_score=85.0)
        msg = _format_vacancy_message(v, locale="ru")
        assert "85%" in msg
        assert "Совместимость" in msg

    def test_includes_compat_score_label_in_english(self):
        v = self._make_vacancy(compatibility_score=72.0)
        msg = _format_vacancy_message(v, locale="en")
        assert "72%" in msg
        assert "Compatibility" in msg

    def test_omits_compat_score_when_absent(self):
        v = self._make_vacancy(compatibility_score=None)
        msg = _format_vacancy_message(v)
        assert "Совместимость" not in msg
        assert "Compatibility" not in msg

    def test_includes_company_when_present(self):
        v = self._make_vacancy(company_name="Acme Corp")
        msg = _format_vacancy_message(v)
        assert "Acme Corp" in msg

    def test_company_line_has_no_leading_blank_line(self):
        v = self._make_vacancy(company_name="Acme Corp")
        msg = _format_vacancy_message(v)
        assert "\n\n" not in msg

    def test_omits_company_line_when_absent(self):
        v = self._make_vacancy(company_name=None)
        msg = _format_vacancy_message(v)
        assert "\U0001f3e2" not in msg

    def test_includes_work_formats_when_present(self):
        v = self._make_vacancy(work_formats="удалённо")
        msg = _format_vacancy_message(v)
        assert "удалённо" in msg

    def test_omits_work_formats_when_absent(self):
        v = self._make_vacancy(work_formats=None)
        msg = _format_vacancy_message(v)
        assert "\U0001f4cd" not in msg

    def test_includes_skills_list_when_present(self):
        v = self._make_vacancy(raw_skills=["Python", "FastAPI", "Docker"])
        msg = _format_vacancy_message(v)
        assert "Python" in msg
        assert "FastAPI" in msg
        assert "Docker" in msg

    def test_omits_skills_line_when_absent(self):
        v = self._make_vacancy(raw_skills=None)
        msg = _format_vacancy_message(v)
        assert "\U0001f527" not in msg

    def test_includes_work_experience_when_present(self):
        v = self._make_vacancy(work_experience="От 3 до 6 лет")
        msg = _format_vacancy_message(v)
        assert "От 3 до 6 лет" in msg

    def test_includes_employment_type_when_present(self):
        v = self._make_vacancy(employment_type="Полная занятость")
        msg = _format_vacancy_message(v)
        assert "Полная занятость" in msg

    def test_message_within_telegram_limit(self):
        v = self._make_vacancy(
            title="X" * 200,
            salary="200 000 ₽",
            company_name="Y" * 200,
            work_formats="удалённо",
            work_experience="От 3 до 6 лет",
            employment_type="Полная занятость",
            work_schedule="Пятидневная рабочая неделя",
            working_hours="Полный день",
            raw_skills=["skill" + str(i) for i in range(50)],
            compatibility_score=99.0,
        )
        msg = _format_vacancy_message(v)
        assert len(msg) <= 4096

    def test_minimal_vacancy_contains_only_title_link(self):
        v = self._make_vacancy()
        msg = _format_vacancy_message(v)
        lines = msg.split("\n")
        assert len(lines) == 1
        assert "<b>" in lines[0]


class TestSendVacanciesIndividually:
    def _make_vacancy(self, title: str = "Dev") -> MagicMock:
        v = MagicMock()
        v.url = "https://hh.ru/vacancy/1"
        v.title = title
        v.salary = None
        v.compatibility_score = None
        v.company_name = None
        v.work_formats = None
        v.work_experience = None
        v.employment_type = None
        v.work_schedule = None
        v.working_hours = None
        v.raw_skills = None
        return v

    @pytest.mark.asyncio
    async def test_sends_one_message_per_vacancy(self):
        bot = MagicMock()
        vacancies = [self._make_vacancy(f"Dev {i}") for i in range(3)]

        with (
            patch(
                "src.services.ai.streaming._send_with_retry",
                new_callable=AsyncMock,
            ) as mock_send,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _send_vacancies_individually(bot, chat_id=123, vacancies=vacancies)

        assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_sleeps_between_messages(self):
        bot = MagicMock()
        vacancies = [self._make_vacancy("Dev A"), self._make_vacancy("Dev B")]

        with (
            patch("src.services.ai.streaming._send_with_retry", new_callable=AsyncMock),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _send_vacancies_individually(bot, chat_id=456, vacancies=vacancies)

        assert mock_sleep.call_count == len(vacancies)
        for call in mock_sleep.call_args_list:
            assert call.args[0] == _INTER_MESSAGE_DELAY_SECONDS

    @pytest.mark.asyncio
    async def test_does_nothing_for_empty_list(self):
        bot = MagicMock()

        with (
            patch(
                "src.services.ai.streaming._send_with_retry",
                new_callable=AsyncMock,
            ) as mock_send,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _send_vacancies_individually(bot, chat_id=789, vacancies=[])

        mock_send.assert_not_called()
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_html_parse_mode(self):
        bot = MagicMock()
        vacancies = [self._make_vacancy()]

        with (
            patch(
                "src.services.ai.streaming._send_with_retry",
                new_callable=AsyncMock,
            ) as mock_send,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _send_vacancies_individually(bot, chat_id=111, vacancies=vacancies)

        _, kwargs = mock_send.call_args
        assert kwargs.get("parse_mode") == "HTML"


class TestResolveCachedVacancy:
    @pytest.mark.asyncio
    async def test_returns_existing_autoparsed_when_found(self):
        existing = MagicMock()
        existing.raw_skills = ["Python"]
        existing.description = "desc"

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=existing)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "123", "url": "http://hh.ru/vacancy/123", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "123", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is existing
        assert returned_vac is vac
        parsed_vacancy_repo.get_by_hh_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_parsed_vacancy_when_not_in_autoparsed(self):
        parsed_record = MagicMock()
        parsed_record.description = "full description"
        parsed_record.raw_skills = ["Python", "FastAPI"]

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "456", "url": "http://hh.ru/vacancy/456", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "456", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is None
        assert returned_vac["description"] == "full description"
        assert returned_vac["raw_skills"] == ["Python", "FastAPI"]
        assert returned_vac["url"] == "http://hh.ru/vacancy/456"

    @pytest.mark.asyncio
    async def test_returns_original_vac_when_not_found_anywhere(self):
        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "789", "url": "http://hh.ru/vacancy/789", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "789", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is None
        assert returned_vac is vac

    @pytest.mark.asyncio
    async def test_uses_empty_strings_when_parsed_vacancy_fields_are_none(self):
        parsed_record = MagicMock()
        parsed_record.description = None
        parsed_record.raw_skills = None

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "999", "cached": True}
        returned_vac, _ = await _resolve_cached_vacancy(
            "999", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_vac["description"] == ""
        assert returned_vac["raw_skills"] == []


class TestDeliverMinCompatFilter:
    """Verify the min_compatibility_percent delivery filter predicate."""

    def _make_vacancy(
        self,
        *,
        compatibility_score: float | None,
        created_at_delta_hours: int = 0,
    ) -> MagicMock:
        from datetime import UTC, datetime, timedelta

        v = MagicMock()
        v.compatibility_score = compatibility_score
        v.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            hours=created_at_delta_hours
        )
        return v

    def _apply_filter(self, vacancies: list, *, min_compat: int) -> list:
        from datetime import UTC, datetime, timedelta

        today = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        return [
            v
            for v in vacancies
            if v.created_at >= today
            and (v.compatibility_score is None or v.compatibility_score >= min_compat)
        ]

    def test_filters_vacancy_below_threshold(self):
        vacancy = self._make_vacancy(compatibility_score=40.0)
        result = self._apply_filter([vacancy], min_compat=50)
        assert result == []

    def test_passes_vacancy_above_threshold(self):
        vacancy = self._make_vacancy(compatibility_score=60.0)
        result = self._apply_filter([vacancy], min_compat=50)
        assert result == [vacancy]

    def test_passes_vacancy_at_exact_threshold(self):
        vacancy = self._make_vacancy(compatibility_score=50.0)
        result = self._apply_filter([vacancy], min_compat=50)
        assert result == [vacancy]

    def test_passes_vacancy_without_score(self):
        vacancy = self._make_vacancy(compatibility_score=None)
        result = self._apply_filter([vacancy], min_compat=50)
        assert result == [vacancy]

    def test_default_threshold_is_50(self):
        ap_settings: dict = {}
        min_compat = ap_settings.get("min_compatibility_percent", 50)

        below = self._make_vacancy(compatibility_score=49.0)
        above = self._make_vacancy(compatibility_score=51.0)
        result = self._apply_filter([below, above], min_compat=min_compat)

        assert below not in result
        assert above in result

    def test_zero_threshold_passes_all_scored_vacancies(self):
        vacancies = [
            self._make_vacancy(compatibility_score=0.0),
            self._make_vacancy(compatibility_score=100.0),
            self._make_vacancy(compatibility_score=None),
        ]
        result = self._apply_filter(vacancies, min_compat=0)
        assert result == vacancies

    def test_excludes_old_vacancies_regardless_of_score(self):
        old = self._make_vacancy(compatibility_score=100.0, created_at_delta_hours=25)
        result = self._apply_filter([old], min_compat=0)
        assert result == []


class TestDeliverLastDeliveredAt:
    """Verify that deliver_autoparse_results only sends vacancies not yet delivered."""

    def _make_session_factory(self, session: MagicMock):
        @asynccontextmanager
        async def factory():
            yield session

        return factory

    def _make_user(self) -> MagicMock:
        user = MagicMock()
        user.language_code = "ru"
        user.timezone = "Europe/Moscow"
        user.autoparse_settings = {}
        user.telegram_id = 100
        return user

    def _make_company(self, *, last_delivered_at: datetime | None = None) -> MagicMock:
        company = MagicMock()
        company.last_delivered_at = last_delivered_at
        company.vacancy_title = "Python Dev"
        return company

    def _make_vacancy(self) -> MagicMock:
        v = MagicMock()
        v.url = "https://hh.ru/vacancy/1"
        v.title = "Dev"
        v.salary = None
        v.compatibility_score = None
        v.company_name = None
        v.work_formats = None
        v.work_experience = None
        v.employment_type = None
        v.work_schedule = None
        v.working_hours = None
        v.raw_skills = None
        return v

    def _make_repos(
        self,
        *,
        user: MagicMock,
        company: MagicMock,
        vacancies: list,
    ) -> tuple[MagicMock, MagicMock, MagicMock]:
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(return_value=vacancies)

        return user_repo, company_repo, vacancy_repo

    @pytest.mark.asyncio
    async def test_uses_last_delivered_at_as_since_when_set(self):
        last_delivered = datetime(2026, 3, 9, 10, 0, 0)
        user = self._make_user()
        company = self._make_company(last_delivered_at=last_delivered)
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        since_used = vacancy_repo.get_new_since.call_args.args[1]
        assert since_used == last_delivered

    @pytest.mark.asyncio
    async def test_falls_back_to_24h_window_when_last_delivered_at_is_none(self):
        user = self._make_user()
        company = self._make_company(last_delivered_at=None)
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        before = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        after = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        since_used = vacancy_repo.get_new_since.call_args.args[1]
        assert before <= since_used <= after

    @pytest.mark.asyncio
    async def test_calls_get_new_since_not_get_by_company(self):
        user = self._make_user()
        company = self._make_company()
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        vacancy_repo.get_new_since.assert_called_once()
        vacancy_repo.get_by_company.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_no_new_vacancies_when_get_new_since_is_empty(self):
        user = self._make_user()
        company = self._make_company()
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "no_new_vacancies"}

    @pytest.mark.asyncio
    async def test_does_not_update_last_delivered_at_when_no_new_vacancies(self):
        user = self._make_user()
        company = self._make_company()
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        company_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_last_delivered_at_after_successful_delivery(self):
        user = self._make_user()
        company = self._make_company()
        vacancies = [self._make_vacancy()]
        user_repo, company_repo, vacancy_repo = self._make_repos(
            user=user, company=company, vacancies=vacancies
        )

        bot_mock = MagicMock()
        bot_mock.session = MagicMock()
        bot_mock.session.close = AsyncMock()

        before = datetime.now(UTC).replace(tzinfo=None)

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch("aiogram.Bot", return_value=bot_mock),
            patch(
                "src.services.ai.streaming._send_with_retry",
                new_callable=AsyncMock,
            ),
            patch(
                "src.worker.tasks.autoparse._send_vacancies_individually",
                new_callable=AsyncMock,
            ),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        after = datetime.now(UTC).replace(tzinfo=None)

        assert result == {"status": "delivered", "count": 1}
        company_repo.update.assert_called_once()
        _, kwargs = company_repo.update.call_args
        assert before <= kwargs["last_delivered_at"] <= after
