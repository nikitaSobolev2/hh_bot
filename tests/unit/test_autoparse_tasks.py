"""Unit tests for autoparse task helper functions."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.services.hh.feed_gating import HhFeedAccountStatus
from src.worker.tasks.autoparse import (
    _build_user_profile,
    _deliver_results_async,
    _resolve_cached_vacancy,
)


def _patch_hh_classify_single():
    """HH account gating: one linked account so delivery tests need no real DB."""
    return patch(
        "src.services.hh.feed_gating.classify_user_hh_accounts",
        AsyncMock(
            return_value=(
                HhFeedAccountStatus.SINGLE,
                [SimpleNamespace(id=1)],
            )
        ),
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
        exp_entry.title = None
        exp_entry.period = None

        stack, exp = _build_user_profile({}, [exp_entry])

        assert "Python" in stack
        assert "FastAPI" in stack
        assert "Acme" in exp
        assert "Python, FastAPI" in exp

    def test_returns_empty_profile_when_no_data(self):
        stack, exp = _build_user_profile({}, [])

        assert stack == []
        assert exp == ""

    def test_formats_experience_from_multiple_entries(self):
        e1 = MagicMock()
        e1.company_name = "Alpha"
        e1.stack = "Go"
        e1.title = None
        e1.period = None
        e2 = MagicMock()
        e2.company_name = "Beta"
        e2.stack = "Rust"
        e2.title = None
        e2.period = None

        _, exp = _build_user_profile({}, [e1, e2])

        assert "Alpha" in exp
        assert "Go" in exp
        assert "Beta" in exp
        assert "Rust" in exp


class TestResolveCachedVacancy:
    @pytest.mark.asyncio
    async def test_returns_existing_autoparsed_when_found(self):
        existing = MagicMock()
        existing.raw_skills = ["Python"]
        existing.description = "desc"

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_company_hh_id_with_employer = AsyncMock(return_value=existing)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id_with_employer = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "123", "url": "http://hh.ru/vacancy/123", "cached": True}
        returned_vac, returned_ap, returned_parsed = await _resolve_cached_vacancy(
            77,
            "123",
            vac,
            vacancy_repo,
            parsed_vacancy_repo,
        )

        assert returned_ap is existing
        assert returned_parsed is None
        assert returned_vac is vac
        vacancy_repo.get_by_company_hh_id_with_employer.assert_awaited_once_with(77, "123")
        parsed_vacancy_repo.get_by_hh_id_with_employer.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_parsed_vacancy_when_not_in_autoparsed(self):
        parsed_record = MagicMock()
        parsed_record.description = "full description"
        parsed_record.raw_skills = ["Python", "FastAPI"]
        parsed_record.employer = None
        parsed_record.experience_name = None
        parsed_record.schedule_name = None
        parsed_record.employment_name = None
        parsed_record.work_format = None

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_company_hh_id_with_employer = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id_with_employer = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "456", "url": "http://hh.ru/vacancy/456", "cached": True}
        returned_vac, returned_ap, returned_parsed = await _resolve_cached_vacancy(
            12,
            "456",
            vac,
            vacancy_repo,
            parsed_vacancy_repo,
        )

        assert returned_ap is None
        assert returned_parsed is parsed_record
        assert returned_vac["description"] == "full description"
        assert returned_vac["raw_skills"] == ["Python", "FastAPI"]
        assert returned_vac["url"] == "http://hh.ru/vacancy/456"

    @pytest.mark.asyncio
    async def test_returns_original_vac_when_not_found_anywhere(self):
        vacancy_repo = MagicMock()
        vacancy_repo.get_by_company_hh_id_with_employer = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id_with_employer = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "789", "url": "http://hh.ru/vacancy/789", "cached": True}
        returned_vac, returned_ap, returned_parsed = await _resolve_cached_vacancy(
            55,
            "789",
            vac,
            vacancy_repo,
            parsed_vacancy_repo,
        )

        assert returned_ap is None
        assert returned_parsed is None
        assert returned_vac is vac

    @pytest.mark.asyncio
    async def test_uses_empty_strings_when_parsed_vacancy_fields_are_none(self):
        parsed_record = MagicMock()
        parsed_record.description = None
        parsed_record.raw_skills = None
        parsed_record.employer = None
        parsed_record.experience_name = None
        parsed_record.schedule_name = None
        parsed_record.employment_name = None
        parsed_record.work_format = None

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_company_hh_id_with_employer = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id_with_employer = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "999", "cached": True}
        returned_vac, _, _ = await _resolve_cached_vacancy(
            99,
            "999",
            vac,
            vacancy_repo,
            parsed_vacancy_repo,
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

    def _make_company(
        self,
        *,
        last_delivered_at: datetime | None = None,
        include_reacted_in_feed: bool = False,
    ) -> MagicMock:
        company = MagicMock()
        company.last_delivered_at = last_delivered_at
        company.vacancy_title = "Python Dev"
        company.is_deleted = False
        company.include_reacted_in_feed = include_reacted_in_feed
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
    ) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.get_by_id_for_user = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(return_value=vacancies)
        vacancy_repo.get_by_ids = AsyncMock(return_value=[])

        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value=set())
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value=set())

        return user_repo, company_repo, vacancy_repo, feed_repo

    def _make_fake_deliver_redis(self) -> MagicMock:
        """In-memory stand-in so unit tests do not connect to Redis for deliver locks."""
        r = MagicMock()
        r.set = MagicMock(return_value=True)
        r.eval = MagicMock(return_value=1)
        r.close = MagicMock()
        return r

    @pytest.mark.asyncio
    async def test_uses_last_delivered_at_as_since_when_set(self):
        last_delivered = datetime(2026, 3, 9, 10, 0, 0)
        user = self._make_user()
        company = self._make_company(last_delivered_at=last_delivered)
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
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
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        before = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
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
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        vacancy_repo.get_new_since.assert_called_once()
        vacancy_repo.get_by_company.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_configured_min_compatibility_to_delivery_queries(self):
        user = self._make_user()
        user.autoparse_settings = {"min_compatibility_percent": 73}
        company = self._make_company()
        queued_vacancy = self._make_vacancy()
        queued_vacancy.id = 5
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user,
            company=company,
            vacancies=[],
        )
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value={5})
        vacancy_repo.get_by_ids = AsyncMock(return_value=[queued_vacancy])

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
            patch(
                "src.services.autoparse_feed_cards.create_feed_session",
                new_callable=AsyncMock,
                return_value=42,
            ),
            patch(
                "src.services.autoparse_feed_cards.send_feed_stats_card",
                new_callable=AsyncMock,
            ),
            _patch_hh_classify_single(),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "delivered", "count": 1}
        assert vacancy_repo.get_new_since.call_args.args[2] == 73
        assert vacancy_repo.get_by_ids.call_args.args == ([5], 73)

    @pytest.mark.asyncio
    async def test_returns_company_not_found_when_company_not_owned_by_user(self):
        user = self._make_user()
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        company_repo = MagicMock()
        company_repo.get_by_id_for_user = AsyncMock(return_value=None)

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 99, 1, force_now=True
            )

        assert result == {"status": "company_not_found"}

    @pytest.mark.asyncio
    async def test_returns_no_new_vacancies_when_get_new_since_is_empty(self):
        user = self._make_user()
        company = self._make_company()
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user, company=company, vacancies=[]
        )

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
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
        user_repo, company_repo, vacancy_repo, _ = self._make_repos(
            user=user, company=company, vacancies=[]
        )
        feed_repo = self._make_feed_repo()

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
        ):
            await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        company_repo.update.assert_not_called()

    def _make_feed_repo(
        self,
        *,
        reacted_ids: set | None = None,
        seen_ids: set | None = None,
    ) -> MagicMock:
        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value=reacted_ids or set())
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value=seen_ids or set())
        return feed_repo

    @pytest.mark.asyncio
    async def test_updates_last_delivered_at_after_successful_delivery(self):
        user = self._make_user()
        company = self._make_company()
        vacancy = self._make_vacancy()
        vacancy.id = 1
        vacancies = [vacancy]
        user_repo, company_repo, vacancy_repo, feed_repo = self._make_repos(
            user=user, company=company, vacancies=vacancies
        )

        before = datetime.now(UTC).replace(tzinfo=None)

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
            patch(
                "src.services.autoparse_feed_cards.create_feed_session",
                new_callable=AsyncMock,
                return_value=42,
            ),
            patch(
                "src.services.autoparse_feed_cards.send_feed_stats_card",
                new_callable=AsyncMock,
            ),
            _patch_hh_classify_single(),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        after = datetime.now(UTC).replace(tzinfo=None)

        assert result == {"status": "delivered", "count": 1}
        company_repo.update.assert_called_once()
        _, kwargs = company_repo.update.call_args
        assert before <= kwargs["last_delivered_at"] <= after


class TestDeliverDedupe:
    """Reschedule must revoke stacked ETA tasks; deliver path must single-flight."""

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

    @pytest.mark.asyncio
    async def test_reschedule_revokes_prior_scheduled_task_id(self):
        """Replacing an ETA deliver must revoke the previous Celery task id."""
        user = self._make_user()
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)

        fake_redis = MagicMock()
        fake_redis.get = MagicMock(return_value="old-celery-task-id")
        fake_redis.set = MagicMock(return_value=True)
        fake_redis.close = MagicMock()

        new_async_result = MagicMock()
        new_async_result.id = "new-task-id"

        moscow = ZoneInfo("Europe/Moscow")

        class _FixedDateTime:
            UTC = UTC
            timedelta = timedelta

            @staticmethod
            def now(tz=None):
                return datetime(2026, 3, 27, 8, 0, 0, tzinfo=tz or moscow)

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch("src.worker.tasks.autoparse._redis_client", return_value=fake_redis),
            patch(
                "src.worker.tasks.autoparse.deliver_autoparse_results.apply_async",
                return_value=new_async_result,
            ) as apply_async,
            patch("src.worker.tasks.autoparse.celery_app.control.revoke") as revoke,
            patch("src.worker.tasks.autoparse.datetime", _FixedDateTime),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 7, 42, force_now=False
            )

        assert result is not None
        assert result.get("status") == "rescheduled"
        assert "eta" in result
        revoke.assert_called_once_with("old-celery-task-id", terminate=False)
        apply_async.assert_called_once()
        fake_redis.get.assert_called_once_with("autoparse:deliver_task:7:42")
        fake_redis.set.assert_called_once()
        assert fake_redis.set.call_args[0][1] == "new-task-id"
        fake_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_deliver_lock_not_acquired(self):
        user = self._make_user()
        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)

        fake_redis = MagicMock()
        fake_redis.set = MagicMock(return_value=False)
        fake_redis.close = MagicMock()

        task = MagicMock()
        task.request.id = "celery-task-1"

        with (
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch("src.worker.tasks.autoparse._redis_client", return_value=fake_redis),
            patch("src.services.autoparse_feed_cards.send_feed_stats_card", AsyncMock()) as send_card,
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), task, 1, 1, force_now=True
            )

        assert result == {"status": "skipped_concurrent_deliver"}
        send_card.assert_not_called()
        fake_redis.close.assert_called_once()


class TestSendRunCompletedNotification:
    def _make_mock_bot(self, send_side_effect=None):
        from unittest.mock import AsyncMock, MagicMock

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=send_side_effect)
        mock_bot.session = MagicMock()
        mock_bot.session.close = AsyncMock()
        return mock_bot

    @pytest.mark.asyncio
    async def test_sends_finished_message_when_new_vacancies_found(self):
        from unittest.mock import patch

        from src.worker.tasks.autoparse import _send_run_completed_notification

        mock_bot = self._make_mock_bot()

        with patch("aiogram.Bot", return_value=mock_bot):
            await _send_run_completed_notification(
                bot_token="fake:token",
                chat_id=12345,
                new_count=3,
                locale="en",
            )

        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "3" in sent_text

    @pytest.mark.asyncio
    async def test_sends_empty_message_when_no_new_vacancies_found(self):
        from unittest.mock import patch

        from src.worker.tasks.autoparse import _send_run_completed_notification

        mock_bot = self._make_mock_bot()

        with patch("aiogram.Bot", return_value=mock_bot):
            await _send_run_completed_notification(
                bot_token="fake:token",
                chat_id=12345,
                new_count=0,
                locale="en",
            )

        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args.kwargs["text"]
        assert "No new vacancies" in sent_text

    @pytest.mark.asyncio
    async def test_closes_bot_session_after_sending(self):
        from unittest.mock import patch

        from src.worker.tasks.autoparse import _send_run_completed_notification

        mock_bot = self._make_mock_bot()

        with patch("aiogram.Bot", return_value=mock_bot):
            await _send_run_completed_notification(
                bot_token="fake:token",
                chat_id=99,
                new_count=1,
                locale="ru",
            )

        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_bot_session_even_when_send_raises(self):
        from unittest.mock import patch

        from src.worker.tasks.autoparse import _send_run_completed_notification

        mock_bot = self._make_mock_bot(send_side_effect=RuntimeError("network error"))

        with (
            patch("aiogram.Bot", return_value=mock_bot),
            pytest.raises(RuntimeError, match="network error"),
        ):
            await _send_run_completed_notification(
                bot_token="fake:token",
                chat_id=99,
                new_count=2,
                locale="ru",
            )

        mock_bot.session.close.assert_called_once()


class TestDeliverSeenIdsFilter:
    """Verify that _deliver_results_async excludes already-seen vacancy IDs."""

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

    def _make_company(self, include_reacted_in_feed: bool = False) -> MagicMock:
        company = MagicMock()
        company.last_delivered_at = datetime(2026, 1, 1, 12, 0, 0)
        company.vacancy_title = "Python Dev"
        company.is_deleted = False
        company.include_reacted_in_feed = include_reacted_in_feed
        return company

    def _make_vacancy(self, vacancy_id: int) -> MagicMock:
        v = MagicMock()
        v.id = vacancy_id
        v.url = f"https://hh.ru/vacancy/{vacancy_id}"
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

    def _make_fake_deliver_redis(self) -> MagicMock:
        r = MagicMock()
        r.set = MagicMock(return_value=True)
        r.eval = MagicMock(return_value=1)
        r.close = MagicMock()
        return r

    @pytest.mark.asyncio
    async def test_excludes_vacancies_already_reacted_to_in_previous_sessions(self):
        """Vacancies the user explicitly liked or disliked are not re-delivered."""
        user = self._make_user()
        company = self._make_company()
        reacted_vacancy = self._make_vacancy(1)
        new_vacancy = self._make_vacancy(2)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.get_by_id_for_user = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()
        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(return_value=[reacted_vacancy, new_vacancy])
        vacancy_repo.get_by_ids = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value={1})
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value={1})

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
            patch(
                "src.services.autoparse_feed_cards.create_feed_session",
                new_callable=AsyncMock,
                return_value=99,
            ) as mock_create,
            patch(
                "src.services.autoparse_feed_cards.send_feed_stats_card",
                new_callable=AsyncMock,
            ),
            _patch_hh_classify_single(),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "delivered", "count": 1}
        passed_ids = mock_create.call_args.kwargs["vacancy_ids"]
        assert passed_ids == [2]

    @pytest.mark.asyncio
    async def test_excludes_reacted_vacancies_even_when_include_reacted_in_feed_is_true(
        self,
    ):
        """Reacted vacancies are always excluded from feed, regardless of setting."""
        user = self._make_user()
        company = self._make_company(include_reacted_in_feed=True)
        reacted_vacancy = self._make_vacancy(1)
        new_vacancy = self._make_vacancy(2)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.get_by_id_for_user = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()
        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(
            return_value=[reacted_vacancy, new_vacancy]
        )
        vacancy_repo.get_by_ids = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value={1})
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value={1})

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
            patch(
                "src.services.autoparse_feed_cards.create_feed_session",
                new_callable=AsyncMock,
                return_value=99,
            ) as mock_create,
            patch(
                "src.services.autoparse_feed_cards.send_feed_stats_card",
                new_callable=AsyncMock,
            ),
            _patch_hh_classify_single(),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "delivered", "count": 1}
        passed_ids = mock_create.call_args.kwargs["vacancy_ids"]
        assert passed_ids == [2]

    @pytest.mark.asyncio
    async def test_returns_no_new_vacancies_when_all_were_reacted_to(self):
        """All new vacancies already reacted to → no_new_vacancies."""
        user = self._make_user()
        company = self._make_company()
        vacancy = self._make_vacancy(1)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.get_by_id_for_user = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()
        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(return_value=[vacancy])
        vacancy_repo.get_by_ids = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value={1})
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value={1})

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "no_new_vacancies"}

    @pytest.mark.asyncio
    async def test_returns_no_new_vacancies_when_get_new_since_empty_and_no_unreviewed(self):
        """No new vacancies and no unreviewed queued vacancies → no_new_vacancies."""
        user = self._make_user()
        company = self._make_company()

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)
        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.get_by_id_for_user = AsyncMock(return_value=company)
        vacancy_repo = MagicMock()
        vacancy_repo.get_new_since = AsyncMock(return_value=[])
        vacancy_repo.get_by_ids = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_reacted_vacancy_ids = AsyncMock(return_value=set())
        feed_repo.get_all_seen_vacancy_ids = AsyncMock(return_value=set())

        with (
            patch(
                "src.worker.tasks.autoparse._redis_client",
                return_value=self._make_fake_deliver_redis(),
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch(
                "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
                return_value=feed_repo,
            ),
        ):
            result = await _deliver_results_async(
                self._make_session_factory(MagicMock()), MagicMock(), 1, 1, force_now=True
            )

        assert result == {"status": "no_new_vacancies"}


class TestGetAllSeenVacancyIds:
    """Verify VacancyFeedSessionRepository.get_all_seen_vacancy_ids."""

    @pytest.mark.asyncio
    async def test_unions_vacancy_ids_from_all_sessions(self):
        from src.repositories.vacancy_feed import VacancyFeedSessionRepository

        session = MagicMock()
        session.execute = AsyncMock(return_value=[([1, 2, 3],), ([3, 4],)])

        repo = VacancyFeedSessionRepository(session)
        seen = await repo.get_all_seen_vacancy_ids(user_id=42, company_id=10)

        assert seen == {1, 2, 3, 4}

    @pytest.mark.asyncio
    async def test_returns_empty_set_when_no_sessions_exist(self):
        from src.repositories.vacancy_feed import VacancyFeedSessionRepository

        session = MagicMock()
        session.execute = AsyncMock(return_value=[])

        repo = VacancyFeedSessionRepository(session)
        seen = await repo.get_all_seen_vacancy_ids(user_id=42, company_id=10)

        assert seen == set()

    @pytest.mark.asyncio
    async def test_handles_single_session_correctly(self):
        from src.repositories.vacancy_feed import VacancyFeedSessionRepository

        session = MagicMock()
        session.execute = AsyncMock(return_value=[([10, 20, 30],)])

        repo = VacancyFeedSessionRepository(session)
        seen = await repo.get_all_seen_vacancy_ids(user_id=1, company_id=5)

        assert seen == {10, 20, 30}


class TestAutoparseLockReentry:
    """Verify the atomic Lua lock correctly handles re-delivery and contention."""

    def test_lua_script_returns_1_when_lock_absent(self):
        """eval returning 1 means the lock was acquired (key did not exist)."""
        r = MagicMock()
        r.eval = MagicMock(return_value=1)

        acquired = r.eval("script", 1, "lock_key", "task-abc", "7200")

        assert acquired == 1

    def test_lua_script_returns_1_for_same_task_redelivery(self):
        """eval returning 1 means re-delivery of the same task is allowed through."""
        r = MagicMock()
        r.eval = MagicMock(return_value=1)

        acquired = r.eval("script", 1, "lock_key", "task-abc", "7200")

        assert acquired == 1

    def test_lua_script_returns_0_when_different_task_holds_lock(self):
        """eval returning 0 means a different task owns the lock — must block."""
        r = MagicMock()
        r.eval = MagicMock(return_value=0)

        acquired = r.eval("script", 1, "lock_key", "other-task-id", "7200")

        assert not acquired

    def test_lock_acquisition_uses_eval_not_get_set(self):
        """Lock must be acquired via a single atomic eval call, not a non-atomic GET+SET."""
        import inspect

        from src.worker.tasks import autoparse as autoparse_module

        source = inspect.getsource(autoparse_module._run_autoparse_company_async)
        assert "r.eval(" in source, "Lock must use r.eval() for atomicity"
        assert "r.get(lock_key)" not in source, (
            "Non-atomic r.get() must not be used for the lock check"
        )


class TestAutoparsCheckpointRestore:
    """Verify checkpoint restore logic initialises analyzed_count correctly."""

    @pytest.mark.asyncio
    async def test_restores_analyzed_offset_from_matching_checkpoint(self):
        """When a checkpoint exists for the same task ID, analyzed_count starts at that offset."""
        import json
        from unittest.mock import AsyncMock, MagicMock

        from src.services.task_checkpoint import TaskCheckpointService

        stored = json.dumps({"task_id": "task-abc", "analyzed": 33, "total": 86})
        redis = MagicMock()
        redis.get = AsyncMock(return_value=stored)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()

        service = TaskCheckpointService(redis)
        result = await service.load("autoparse:42", "task-abc")
        analyzed_offset, original_total = result if result else (0, 86)

        assert analyzed_offset == 33
        assert original_total == 86

    @pytest.mark.asyncio
    async def test_starts_from_zero_when_no_checkpoint_exists(self):
        """With no prior checkpoint, analyzed_count starts at 0."""
        from unittest.mock import AsyncMock, MagicMock

        from src.services.task_checkpoint import TaskCheckpointService

        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)

        service = TaskCheckpointService(redis)
        total_to_analyze = 50
        result = await service.load("autoparse:42", "task-new")
        analyzed_offset, original_total = result if result else (0, total_to_analyze)

        assert analyzed_offset == 0
        assert original_total == 50

    @pytest.mark.asyncio
    async def test_ignores_stale_checkpoint_from_different_task(self):
        """A checkpoint written by a different task run must not restore."""
        import json
        from unittest.mock import AsyncMock, MagicMock

        from src.services.task_checkpoint import TaskCheckpointService

        stored = json.dumps({"task_id": "old-task", "analyzed": 20, "total": 50})
        redis = MagicMock()
        redis.get = AsyncMock(return_value=stored)

        service = TaskCheckpointService(redis)
        total_to_analyze = 50
        result = await service.load("autoparse:42", "new-task")
        analyzed_offset, original_total = result if result else (0, total_to_analyze)

        assert analyzed_offset == 0
        assert original_total == 50

    @pytest.mark.asyncio
    async def test_checkpoint_clears_on_success(self):
        """After successful completion the checkpoint key must be deleted."""
        from unittest.mock import AsyncMock, MagicMock

        from src.services.task_checkpoint import TaskCheckpointService

        redis = MagicMock()
        redis.delete = AsyncMock()

        service = TaskCheckpointService(redis)
        await service.clear("autoparse:42")

        redis.delete.assert_called_once_with("checkpoint:autoparse:42")


class TestUpdateCompatUnseen:
    """Unit tests for update_compatibility_unseen_vacancies task."""

    def _make_session_factory(self, session: MagicMock):
        @asynccontextmanager
        async def factory():
            yield session

        return factory

    @pytest.mark.asyncio
    async def test_returns_no_tech_stack_when_empty(self):
        """When user has no tech_stack and no work experiences, return no_tech_stack."""
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.autoparse_settings = {}
        mock_user.telegram_id = 100
        mock_user.language_code = "ru"

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)
        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])

        mock_task = MagicMock()
        mock_task.acquire_user_task_lock = AsyncMock(return_value=True)
        mock_task.release_user_task_lock = AsyncMock()
        mock_task.acquire_user_vacancy_processing_lock = AsyncMock(return_value=True)
        mock_task.release_user_vacancy_processing_lock = AsyncMock()

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        @asynccontextmanager
        async def session_factory():
            yield mock_session

        with patch(
            "src.repositories.app_settings.AppSettingRepository",
            return_value=settings_repo,
        ), patch(
            "src.repositories.user.UserRepository",
            return_value=user_repo,
        ), patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=we_repo,
        ):
            from src.worker.tasks.autoparse import _update_compat_unseen_async

            result = await _update_compat_unseen_async(
                session_factory, mock_task, user_id=1
            )

        assert result["status"] == "no_tech_stack"

    @pytest.mark.asyncio
    async def test_returns_already_running_when_lock_not_acquired(self):
        """When lock is held by another task, return already_running."""
        mock_task = MagicMock()
        mock_task.acquire_user_task_lock = AsyncMock(return_value=False)
        mock_task.release_user_task_lock = AsyncMock()
        mock_task.acquire_user_vacancy_processing_lock = AsyncMock()
        mock_task.release_user_vacancy_processing_lock = AsyncMock()

        session_factory = MagicMock()

        from src.worker.tasks.autoparse import _update_compat_unseen_async

        result = await _update_compat_unseen_async(
            session_factory, mock_task, user_id=1
        )

        assert result["status"] == "already_running"
        mock_task.release_user_task_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_ai_and_updates_db_when_vacancies_exist(self):
        """When vacancies exist, analyze_vacancies_batch is called and DB is updated."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.autoparse_settings = {"tech_stack": ["Python"]}
        mock_user.telegram_id = 100
        mock_user.language_code = "ru"

        mock_vacancy = MagicMock()
        mock_vacancy.id = 10
        mock_vacancy.hh_vacancy_id = "123"
        mock_vacancy.title = "Python Dev"
        mock_vacancy.raw_skills = ["Python"]
        mock_vacancy.description = "Great job"
        mock_vacancy.snippet_requirement = None
        mock_vacancy.snippet_responsibility = None
        mock_vacancy.experience_name = None
        mock_vacancy.schedule_name = None
        mock_vacancy.employment_name = None
        mock_vacancy.employment_form_name = None
        mock_vacancy.work_format = None
        mock_vacancy.professional_roles = None

        from src.services.ai.client import VacancyAnalysis

        mock_analysis = VacancyAnalysis(
            summary="Good match", stack=["Python"], compatibility_score=75.0
        )

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def session_factory():
            yield mock_session

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)
        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_liked_vacancy_ids_for_user = AsyncMock(return_value=set())
        feed_repo.get_all_disliked_vacancy_ids_for_user = AsyncMock(return_value=set())
        vacancy_repo = MagicMock()
        vacancy_repo.get_unseen_for_user = AsyncMock(return_value=[mock_vacancy])
        vacancy_repo.get_by_id = AsyncMock(return_value=mock_vacancy)
        vacancy_repo.update = AsyncMock()

        mock_ai_client = MagicMock()
        mock_ai_client.analyze_vacancies_batch = AsyncMock(
            return_value={"123": mock_analysis}
        )

        mock_task = MagicMock()
        mock_task.acquire_user_task_lock = AsyncMock(return_value=True)
        mock_task.release_user_task_lock = AsyncMock()
        mock_task.acquire_user_vacancy_processing_lock = AsyncMock(return_value=True)
        mock_task.release_user_vacancy_processing_lock = AsyncMock()

        with patch(
            "src.repositories.app_settings.AppSettingRepository",
            return_value=settings_repo,
        ), patch(
            "src.repositories.user.UserRepository",
            return_value=user_repo,
        ), patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=we_repo,
        ), patch(
            "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
            return_value=feed_repo,
        ), patch(
            "src.repositories.autoparse.AutoparsedVacancyRepository",
            return_value=vacancy_repo,
        ), patch(
            "src.services.ai.client.AIClient",
            return_value=mock_ai_client,
        ), patch(
            "src.worker.circuit_breaker.CircuitBreaker",
        ), patch(
            "src.config.settings",
            bot_token="fake",
        ), patch(
            "src.core.i18n.get_text",
            side_effect=lambda key, locale, **kw: key,
        ), patch(
            "aiogram.Bot",
        ) as mock_bot_cls:
            mock_bot_instance = MagicMock()
            mock_bot_instance.send_message = AsyncMock()
            mock_bot_instance.session.close = AsyncMock()
            mock_bot_cls.return_value = mock_bot_instance

            from src.worker.tasks.autoparse import _update_compat_unseen_async

            result = await _update_compat_unseen_async(
                session_factory,
                mock_task,
                user_id=1,
            )

        assert result["status"] == "completed"
        assert result["updated_count"] == 1
        mock_ai_client.analyze_vacancies_batch.assert_called_once()
        vacancy_repo.update.assert_called()
        mock_task.acquire_user_vacancy_processing_lock.assert_awaited_once_with(
            1,
            "123",
            ttl=1800,
        )
        mock_task.release_user_vacancy_processing_lock.assert_awaited_once_with(1, "123")

    @pytest.mark.asyncio
    async def test_skips_ai_when_vacancy_processing_lock_not_acquired(self):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.autoparse_settings = {"tech_stack": ["Python"]}
        mock_user.telegram_id = 100
        mock_user.language_code = "ru"

        mock_vacancy = MagicMock()
        mock_vacancy.id = 10
        mock_vacancy.hh_vacancy_id = "123"
        mock_vacancy.title = "Python Dev"
        mock_vacancy.raw_skills = ["Python"]
        mock_vacancy.description = "Great job"
        mock_vacancy.snippet_requirement = None
        mock_vacancy.snippet_responsibility = None
        mock_vacancy.experience_name = None
        mock_vacancy.schedule_name = None
        mock_vacancy.employment_name = None
        mock_vacancy.employment_form_name = None
        mock_vacancy.work_format = None
        mock_vacancy.professional_roles = None

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def session_factory():
            yield mock_session

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=mock_user)
        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)
        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])
        feed_repo = MagicMock()
        feed_repo.get_all_liked_vacancy_ids_for_user = AsyncMock(return_value=set())
        feed_repo.get_all_disliked_vacancy_ids_for_user = AsyncMock(return_value=set())
        vacancy_repo = MagicMock()
        vacancy_repo.get_unseen_for_user = AsyncMock(return_value=[mock_vacancy])
        vacancy_repo.get_by_id = AsyncMock(return_value=mock_vacancy)
        vacancy_repo.update = AsyncMock()

        mock_ai_client = MagicMock()
        mock_ai_client.analyze_vacancies_batch = AsyncMock()

        mock_task = MagicMock()
        mock_task.acquire_user_task_lock = AsyncMock(return_value=True)
        mock_task.release_user_task_lock = AsyncMock()
        mock_task.acquire_user_vacancy_processing_lock = AsyncMock(return_value=False)
        mock_task.release_user_vacancy_processing_lock = AsyncMock()

        with patch(
            "src.repositories.app_settings.AppSettingRepository",
            return_value=settings_repo,
        ), patch(
            "src.repositories.user.UserRepository",
            return_value=user_repo,
        ), patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=we_repo,
        ), patch(
            "src.repositories.vacancy_feed.VacancyFeedSessionRepository",
            return_value=feed_repo,
        ), patch(
            "src.repositories.autoparse.AutoparsedVacancyRepository",
            return_value=vacancy_repo,
        ), patch(
            "src.services.ai.client.AIClient",
            return_value=mock_ai_client,
        ), patch(
            "src.worker.circuit_breaker.CircuitBreaker",
        ), patch(
            "src.config.settings",
            bot_token="fake",
        ), patch(
            "src.core.i18n.get_text",
            side_effect=lambda key, locale, **kw: key,
        ), patch(
            "aiogram.Bot",
        ) as mock_bot_cls:
            mock_bot_instance = MagicMock()
            mock_bot_instance.send_message = AsyncMock()
            mock_bot_instance.session.close = AsyncMock()
            mock_bot_cls.return_value = mock_bot_instance

            from src.worker.tasks.autoparse import _update_compat_unseen_async

            result = await _update_compat_unseen_async(
                session_factory,
                mock_task,
                user_id=1,
            )

        assert result["status"] == "completed"
        assert result["updated_count"] == 0
        mock_ai_client.analyze_vacancies_batch.assert_not_called()
        vacancy_repo.update.assert_not_called()
        mock_task.release_user_vacancy_processing_lock.assert_not_called()
