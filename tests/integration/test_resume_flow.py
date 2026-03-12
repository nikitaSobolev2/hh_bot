"""Integration-style tests for the resume generation flow handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_callback(text: str = "test") -> MagicMock:
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock(return_value=MagicMock(message_id=42))
    callback.message.answer = AsyncMock(return_value=MagicMock(message_id=43))
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.message_id = 10
    callback.answer = AsyncMock()
    return callback


def _make_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock(return_value=MagicMock(message_id=44))
    msg.chat = MagicMock()
    msg.chat.id = 123
    msg.message_id = 11
    return msg


def _make_user() -> MagicMock:
    user = MagicMock()
    user.id = 1
    user.language_code = "ru"
    return user


def _make_state(data: dict | None = None) -> MagicMock:
    state = MagicMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.get = MagicMock(side_effect=lambda key, **kw: key)
    return i18n


def _make_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


class TestHandleStart:
    @pytest.mark.asyncio
    async def test_clears_state_and_asks_for_job_title(self):
        from src.bot.modules.resume.handlers import handle_start

        callback = _make_callback()
        state = _make_state()
        i18n = _make_i18n()

        await handle_start(callback, state, i18n)

        state.clear.assert_awaited_once()
        state.set_state.assert_awaited_once()
        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()


class TestFsmJobTitle:
    @pytest.mark.asyncio
    async def test_saves_title_and_asks_for_skill_level(self):
        from src.bot.modules.resume.handlers import fsm_job_title

        message = _make_message("Python Developer")
        state = _make_state()
        i18n = _make_i18n()

        await fsm_job_title(message, state, i18n)

        state.update_data.assert_awaited()
        update_call = state.update_data.await_args_list[0]
        assert update_call.kwargs.get("res_job_title") == "Python Developer"
        state.set_state.assert_awaited_once()
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_empty_title(self):
        from src.bot.modules.resume.handlers import fsm_job_title

        message = _make_message("")
        state = _make_state()
        i18n = _make_i18n()

        await fsm_job_title(message, state, i18n)

        state.update_data.assert_not_awaited()
        state.set_state.assert_not_awaited()


class TestHandleToggleExp:
    @pytest.mark.asyncio
    async def test_disables_experience(self):
        from src.bot.modules.resume.handlers import handle_toggle_exp

        callback = _make_callback()
        callback_data = MagicMock()
        callback_data.work_exp_id = 5
        state = _make_state({"res_disabled_exp_ids": []})
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        with patch(
            "src.bot.modules.resume.handlers._show_work_experience_step",
            new=AsyncMock(),
        ):
            await handle_toggle_exp(callback, callback_data, user, state, session, i18n)

        update_call = state.update_data.await_args_list[0]
        assert 5 in update_call.kwargs.get("res_disabled_exp_ids", [])

    @pytest.mark.asyncio
    async def test_re_enables_already_disabled_experience(self):
        from src.bot.modules.resume.handlers import handle_toggle_exp

        callback = _make_callback()
        callback_data = MagicMock()
        callback_data.work_exp_id = 5
        state = _make_state({"res_disabled_exp_ids": [5]})
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        with patch(
            "src.bot.modules.resume.handlers._show_work_experience_step",
            new=AsyncMock(),
        ):
            await handle_toggle_exp(callback, callback_data, user, state, session, i18n)

        update_call = state.update_data.await_args_list[0]
        assert 5 not in update_call.kwargs.get("res_disabled_exp_ids", [5])


class TestHandleCancel:
    @pytest.mark.asyncio
    async def test_clears_state_and_shows_start_keyboard(self):
        from src.bot.modules.resume.handlers import handle_cancel

        callback = _make_callback()
        state = _make_state()
        i18n = _make_i18n()

        await handle_cancel(callback, state, i18n)

        state.clear.assert_awaited_once()
        callback.message.edit_text.assert_awaited_once()
        callback.answer.assert_awaited_once()


class TestParseKeyphrasesByCompany:
    def test_empty_string_returns_empty_dict(self):
        from src.worker.tasks.work_experience import _parse_keyphrases_by_company

        assert _parse_keyphrases_by_company("") == {}

    def test_single_company_parsed(self):
        from src.worker.tasks.work_experience import _parse_keyphrases_by_company

        raw = "Компания: Acme\n- phrase one\n- phrase two"
        result = _parse_keyphrases_by_company(raw)
        assert "Acme" in result

    def test_multiple_companies_parsed(self):
        from src.worker.tasks.work_experience import _parse_keyphrases_by_company

        raw = "Компания: Alpha\n- phrase A\n\nКомпания: Beta\n- phrase B"
        result = _parse_keyphrases_by_company(raw)
        assert "Alpha" in result
        assert "Beta" in result


class TestFsmRecSpeakerName:
    @pytest.mark.asyncio
    async def test_saves_name_and_advances_to_position(self):
        from src.bot.modules.resume.handlers import fsm_rec_speaker_name

        message = _make_message("Иван Петров")
        state = _make_state({"res_current_rec_exp_id": 3})
        i18n = _make_i18n()

        await fsm_rec_speaker_name(message, state, i18n)

        update_call = state.update_data.await_args_list[0]
        assert update_call.kwargs.get("res_rec_speaker_name") == "Иван Петров"
        state.set_state.assert_awaited_once()
        message.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejects_empty_name(self):
        from src.bot.modules.resume.handlers import fsm_rec_speaker_name

        message = _make_message("")
        state = _make_state({"res_current_rec_exp_id": 3})
        i18n = _make_i18n()

        await fsm_rec_speaker_name(message, state, i18n)

        state.update_data.assert_not_awaited()
        state.set_state.assert_not_awaited()
