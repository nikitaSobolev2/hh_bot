"""Unit tests for the parsing retry FSM flow and event loop fix."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext


def _make_i18n() -> I18nContext:
    return I18nContext(locale="en")


def _make_company(
    company_id: int = 1,
    user_id: int = 42,
    target_count: int = 50,
    keyword_filter: str = "",
    vacancy_title: str = "Python Developer",
) -> MagicMock:
    company = MagicMock()
    company.id = company_id
    company.user_id = user_id
    company.target_count = target_count
    company.keyword_filter = keyword_filter
    company.vacancy_title = vacancy_title
    return company


def _make_user(user_id: int = 42) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _make_callback(chat_id: int = 100) -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat.id = chat_id
    return callback


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


class TestParsingRetryEntersFSM:
    @pytest.mark.asyncio
    async def test_sets_retry_count_state_and_shows_prompt(self):
        from src.bot.modules.parsing.handlers import parsing_retry
        from src.bot.modules.parsing.states import ParsingForm

        company = _make_company(target_count=30)
        callback = _make_callback()
        state = _make_state()

        with patch(
            "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
            new_callable=AsyncMock,
            return_value=company,
        ):
            await parsing_retry(
                callback,
                MagicMock(company_id=company.id),
                _make_user(),
                MagicMock(),
                state,
                _make_i18n(),
            )

        state.set_state.assert_awaited_once_with(ParsingForm.retry_count)
        state.update_data.assert_awaited_once_with(
            retry_company_id=company.id,
            retry_default_count=company.target_count,
        )
        callback.message.edit_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shows_alert_when_company_not_found(self):
        from src.bot.modules.parsing.handlers import parsing_retry

        callback = _make_callback()
        state = _make_state()

        with patch(
            "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await parsing_retry(
                callback,
                MagicMock(company_id=99),
                _make_user(),
                MagicMock(),
                state,
                _make_i18n(),
            )

        callback.answer.assert_awaited_once()
        state.set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shows_alert_when_company_belongs_to_another_user(self):
        from src.bot.modules.parsing.handlers import parsing_retry

        company = _make_company(user_id=999)
        callback = _make_callback()
        state = _make_state()

        with patch(
            "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
            new_callable=AsyncMock,
            return_value=company,
        ):
            await parsing_retry(
                callback,
                MagicMock(company_id=company.id),
                _make_user(user_id=42),
                MagicMock(),
                state,
                _make_i18n(),
            )

        state.set_state.assert_not_awaited()


class TestParsingRetryUseDefault:
    @pytest.mark.asyncio
    async def test_uses_stored_default_count_from_state(self):
        from src.bot.modules.parsing.handlers import parsing_retry_use_default

        company = _make_company(target_count=50)
        state = _make_state(data={"retry_company_id": company.id, "retry_default_count": 50})
        callback = _make_callback()

        with (
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
                new_callable=AsyncMock,
                return_value=company,
            ),
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.clone_and_dispatch",
                new_callable=AsyncMock,
                return_value=99,
            ) as mock_clone,
        ):
            await parsing_retry_use_default(
                callback,
                MagicMock(company_id=company.id),
                _make_user(),
                MagicMock(),
                state,
                _make_i18n(),
            )

        mock_clone.assert_awaited_once()
        _, kwargs = mock_clone.call_args
        assert kwargs.get("target_count") == 50

    @pytest.mark.asyncio
    async def test_clears_state_after_dispatch(self):
        from src.bot.modules.parsing.handlers import parsing_retry_use_default

        company = _make_company(target_count=50)
        state = _make_state(data={"retry_company_id": company.id, "retry_default_count": 50})
        callback = _make_callback()

        with (
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
                new_callable=AsyncMock,
                return_value=company,
            ),
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.clone_and_dispatch",
                new_callable=AsyncMock,
                return_value=99,
            ),
        ):
            await parsing_retry_use_default(
                callback,
                MagicMock(company_id=company.id),
                _make_user(),
                MagicMock(),
                state,
                _make_i18n(),
            )

        state.clear.assert_awaited_once()


class TestFsmRetryCount:
    @pytest.mark.asyncio
    async def test_dispatches_with_custom_count(self):
        from src.bot.modules.parsing.handlers import fsm_retry_count

        company = _make_company()
        state = _make_state(data={"retry_company_id": company.id})
        message = AsyncMock()
        message.text = "75"
        message.chat.id = 100

        with (
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
                new_callable=AsyncMock,
                return_value=company,
            ),
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.clone_and_dispatch",
                new_callable=AsyncMock,
                return_value=99,
            ) as mock_clone,
        ):
            await fsm_retry_count(
                message,
                _make_user(),
                state,
                MagicMock(),
                _make_i18n(),
            )

        mock_clone.assert_awaited_once()
        _, kwargs = mock_clone.call_args
        assert kwargs.get("target_count") == 75

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_input", ["0", "-5", "abc", "201", "0.5", ""])
    async def test_rejects_invalid_input(self, bad_input: str):
        from src.bot.modules.parsing.handlers import fsm_retry_count

        state = _make_state()
        message = AsyncMock()
        message.text = bad_input

        with patch(
            "src.bot.modules.parsing.handlers.parsing_service.clone_and_dispatch",
            new_callable=AsyncMock,
        ) as mock_clone:
            await fsm_retry_count(
                message,
                _make_user(),
                state,
                MagicMock(),
                _make_i18n(),
            )

        mock_clone.assert_not_awaited()
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clears_state_after_successful_dispatch(self):
        from src.bot.modules.parsing.handlers import fsm_retry_count

        company = _make_company()
        state = _make_state(data={"retry_company_id": company.id})
        message = AsyncMock()
        message.text = "30"
        message.chat.id = 100

        with (
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.get_company_by_id",
                new_callable=AsyncMock,
                return_value=company,
            ),
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.clone_and_dispatch",
                new_callable=AsyncMock,
                return_value=99,
            ),
        ):
            await fsm_retry_count(
                message,
                _make_user(),
                state,
                MagicMock(),
                _make_i18n(),
            )

        state.clear.assert_awaited_once()


class TestParsingRetryCancel:
    @pytest.mark.asyncio
    async def test_clears_state_and_shows_list(self):
        from src.bot.modules.parsing.handlers import parsing_retry_cancel

        state = _make_state()
        callback = _make_callback()
        session = MagicMock()
        user = _make_user()

        with (
            patch(
                "src.bot.modules.parsing.handlers.show_parsing_list",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "src.bot.modules.parsing.handlers.parsing_service.get_user_companies",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await parsing_retry_cancel(callback, user, state, session, _make_i18n())

        state.clear.assert_awaited_once()
        mock_list.assert_awaited_once()


class TestCloneAndDispatchTargetCount:
    @pytest.mark.asyncio
    async def test_uses_override_count_when_provided(self):
        from src.bot.modules.parsing.services import clone_and_dispatch

        source = MagicMock()
        source.vacancy_title = "Dev"
        source.search_url = "https://hh.ru/search"
        source.keyword_filter = ""
        source.target_count = 50

        with (
            patch("src.bot.modules.parsing.services.ParsingCompanyRepository") as mock_repo_cls,
            patch(
                "src.bot.modules.parsing.services.create_parsing_company",
                new_callable=AsyncMock,
                return_value=10,
            ) as mock_create,
            patch("src.bot.modules.parsing.services.dispatch_parsing_task"),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_by_id = AsyncMock(return_value=source)
            mock_repo_cls.return_value = repo_instance

            session = MagicMock()
            await clone_and_dispatch(session, 1, 42, target_count=25)

        _, kwargs = mock_create.call_args
        assert kwargs["target_count"] == 25

    @pytest.mark.asyncio
    async def test_uses_source_count_when_override_is_none(self):
        from src.bot.modules.parsing.services import clone_and_dispatch

        source = MagicMock()
        source.vacancy_title = "Dev"
        source.search_url = "https://hh.ru/search"
        source.keyword_filter = ""
        source.target_count = 50

        with (
            patch("src.bot.modules.parsing.services.ParsingCompanyRepository") as mock_repo_cls,
            patch(
                "src.bot.modules.parsing.services.create_parsing_company",
                new_callable=AsyncMock,
                return_value=10,
            ) as mock_create,
            patch("src.bot.modules.parsing.services.dispatch_parsing_task"),
        ):
            repo_instance = AsyncMock()
            repo_instance.get_by_id = AsyncMock(return_value=source)
            mock_repo_cls.return_value = repo_instance

            session = MagicMock()
            await clone_and_dispatch(session, 1, 42)

        _, kwargs = mock_create.call_args
        assert kwargs["target_count"] == 50


class TestRunAsyncClosedLoopSuppression:
    def test_suppresses_event_loop_closed_error(self):
        from src.worker.utils import _suppress_closed_loop_errors

        loop = MagicMock()
        context = {"exception": RuntimeError("Event loop is closed")}

        _suppress_closed_loop_errors(loop, context)

        loop.default_exception_handler.assert_not_called()

    def test_passes_through_other_runtime_errors(self):
        from src.worker.utils import _suppress_closed_loop_errors

        loop = MagicMock()
        context = {"exception": RuntimeError("Something else went wrong")}

        _suppress_closed_loop_errors(loop, context)

        loop.default_exception_handler.assert_called_once_with(context)

    def test_passes_through_non_runtime_exceptions(self):
        from src.worker.utils import _suppress_closed_loop_errors

        loop = MagicMock()
        context = {"exception": ValueError("bad value")}

        _suppress_closed_loop_errors(loop, context)

        loop.default_exception_handler.assert_called_once_with(context)

    def test_passes_through_context_without_exception(self):
        from src.worker.utils import _suppress_closed_loop_errors

        loop = MagicMock()
        context = {"message": "some warning"}

        _suppress_closed_loop_errors(loop, context)

        loop.default_exception_handler.assert_called_once_with(context)

    def test_run_async_installs_exception_handler(self):
        """Verify run_async installs the suppress handler before executing the task."""
        from src.worker.utils import _suppress_closed_loop_errors, run_async

        captured: dict = {}

        async def capture_handler(session_factory):
            loop = asyncio.get_running_loop()
            captured["handler"] = loop.get_exception_handler()
            await asyncio.sleep(0)
            return "done"

        result = run_async(capture_handler)

        assert result == "done"
        assert captured.get("handler") is _suppress_closed_loop_errors
