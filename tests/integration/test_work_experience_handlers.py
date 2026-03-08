"""Integration tests for work experience handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.parsing.callbacks import KeyPhrasesCallback, WorkExperienceCallback


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.is_admin = False
    user.language_code = "ru"
    return user


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.get = MagicMock(side_effect=lambda key, **kw: key)
    return i18n


def _make_callback(callback_data) -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.data = callback_data.pack()
    callback.answer = AsyncMock()
    return callback


def _make_state() -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_experience(exp_id, name, stack):
    exp = MagicMock()
    exp.id = exp_id
    exp.company_name = name
    exp.stack = stack
    exp.is_active = True
    exp.created_at = MagicMock()
    exp.created_at.strftime = MagicMock(return_value="01/01")
    return exp


class TestKeyPhrasesStartShowsWorkExperience:
    @pytest.mark.asyncio
    async def test_start_shows_work_experience_step(self, mock_session):
        from src.bot.modules.parsing.handlers import key_phrases_start

        callback_data = KeyPhrasesCallback(company_id=1, action="start")
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.get_active_work_experiences = AsyncMock(return_value=[])
            await key_phrases_start(callback, callback_data, user, state, mock_session, i18n)

        state.clear.assert_called_once()
        callback.message.edit_text.assert_called_once()
        call_text = callback.message.edit_text.call_args.args[0]
        assert "work-exp-prompt" in call_text


class TestWorkExpAdd:
    @pytest.mark.asyncio
    async def test_add_sets_fsm_state(self, mock_session):
        from src.bot.modules.parsing.handlers import work_exp_add

        callback_data = WorkExperienceCallback(action="add", company_id=5)
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.count_active_work_experiences = AsyncMock(return_value=2)
            await work_exp_add(callback, callback_data, user, state, mock_session, i18n)

        state.set_state.assert_called_once()
        state.update_data.assert_called_once_with(we_company_id=5)

    @pytest.mark.asyncio
    async def test_add_blocked_at_max(self, mock_session):
        from src.bot.modules.parsing.handlers import work_exp_add

        callback_data = WorkExperienceCallback(action="add", company_id=5)
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.count_active_work_experiences = AsyncMock(return_value=6)
            await work_exp_add(callback, callback_data, user, state, mock_session, i18n)

        state.set_state.assert_not_called()
        callback.answer.assert_called_once()


class TestWorkExpCompanyName:
    @pytest.mark.asyncio
    async def test_valid_name_advances_to_stack(self):
        from src.bot.modules.parsing.handlers import fsm_work_exp_company_name

        message = AsyncMock()
        message.text = "Google"
        user = _make_user()
        state = _make_state()
        state.get_data.return_value = {"we_company_id": 1}
        i18n = _make_i18n()

        await fsm_work_exp_company_name(message, user, state, i18n)

        state.update_data.assert_called_once_with(we_company_name="Google")
        state.set_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_name_rejected(self):
        from src.bot.modules.parsing.handlers import fsm_work_exp_company_name

        message = AsyncMock()
        message.text = "   "
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await fsm_work_exp_company_name(message, user, state, i18n)

        state.set_state.assert_not_called()
        message.answer.assert_called_once()


class TestWorkExpStack:
    @pytest.mark.asyncio
    async def test_valid_stack_saves_and_returns(self, mock_session):
        from src.bot.modules.parsing.handlers import fsm_work_exp_stack

        message = AsyncMock()
        message.text = "Python, Django"
        user = _make_user()
        state = _make_state()
        state.get_data.return_value = {
            "we_company_id": 1,
            "we_company_name": "Google",
        }
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.add_work_experience = AsyncMock()
            mock_service.get_active_work_experiences = AsyncMock(return_value=[])
            await fsm_work_exp_stack(message, user, state, mock_session, i18n)

        state.clear.assert_called_once()
        mock_service.add_work_experience.assert_called_once_with(
            mock_session, user.id, "Google", "Python, Django"
        )

    @pytest.mark.asyncio
    async def test_empty_stack_rejected(self, mock_session):
        from src.bot.modules.parsing.handlers import fsm_work_exp_stack

        message = AsyncMock()
        message.text = "  "
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await fsm_work_exp_stack(message, user, state, mock_session, i18n)

        state.clear.assert_not_called()
        message.answer.assert_called_once()


class TestWorkExpRemove:
    @pytest.mark.asyncio
    async def test_remove_deactivates_and_refreshes(self, mock_session):
        from src.bot.modules.parsing.handlers import work_exp_remove

        callback_data = WorkExperienceCallback(action="remove", company_id=5, work_exp_id=42)
        callback = _make_callback(callback_data)
        user = _make_user()
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.deactivate_work_experience = AsyncMock()
            mock_service.get_active_work_experiences = AsyncMock(return_value=[])
            await work_exp_remove(callback, callback_data, user, mock_session, i18n)

        mock_service.deactivate_work_experience.assert_called_once_with(mock_session, 42, user.id)


class TestWorkExpSkip:
    @pytest.mark.asyncio
    async def test_skip_goes_to_count_step(self):
        from src.bot.modules.parsing.handlers import work_exp_skip

        callback_data = WorkExperienceCallback(action="skip", company_id=5)
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await work_exp_skip(callback, callback_data, user, state, i18n)

        state.set_state.assert_called_once()
        state.update_data.assert_called_once_with(kp_company_id=5)
        call_text = callback.message.edit_text.call_args.args[0]
        assert "keyphrase-count-prompt" in call_text


class TestWorkExpContinue:
    @pytest.mark.asyncio
    async def test_continue_goes_to_per_company_count(self):
        from src.bot.modules.parsing.handlers import work_exp_continue

        callback_data = WorkExperienceCallback(action="continue", company_id=5)
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await work_exp_continue(callback, callback_data, user, state, i18n)

        state.set_state.assert_called_once()
        state.update_data.assert_called_once_with(kp_company_id=5)
        call_text = callback.message.edit_text.call_args.args[0]
        assert "keyphrase-per-company-count" in call_text


class TestWorkExpCancelAdd:
    @pytest.mark.asyncio
    async def test_cancel_clears_state_and_returns(self, mock_session):
        from src.bot.modules.parsing.handlers import work_exp_cancel_add

        callback_data = WorkExperienceCallback(action="cancel_add", company_id=5)
        callback = _make_callback(callback_data)
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        with patch("src.bot.modules.parsing.handlers.parsing_service") as mock_service:
            mock_service.get_active_work_experiences = AsyncMock(return_value=[])
            await work_exp_cancel_add(callback, callback_data, user, state, mock_session, i18n)

        state.clear.assert_called_once()
        callback.message.edit_text.assert_called_once()


class TestPerCompanyCount:
    @pytest.mark.asyncio
    async def test_valid_count_proceeds_to_language(self):
        from src.bot.modules.parsing.handlers import fsm_per_company_count

        message = AsyncMock()
        message.text = "4"
        user = _make_user()
        state = _make_state()
        state.get_data.return_value = {"kp_company_id": 5}
        i18n = _make_i18n()

        await fsm_per_company_count(message, user, state, i18n)

        state.clear.assert_called_once()
        message.answer.assert_called_once()
        call_text = message.answer.call_args.args[0]
        assert "keyphrase-select-lang" in call_text

    @pytest.mark.asyncio
    async def test_count_over_8_rejected(self):
        from src.bot.modules.parsing.handlers import fsm_per_company_count

        message = AsyncMock()
        message.text = "9"
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await fsm_per_company_count(message, user, state, i18n)

        state.clear.assert_not_called()
        message.answer.assert_called_once()
        assert "keyphrase-max-8" in message.answer.call_args.args[0]

    @pytest.mark.asyncio
    async def test_non_numeric_rejected(self):
        from src.bot.modules.parsing.handlers import fsm_per_company_count

        message = AsyncMock()
        message.text = "abc"
        user = _make_user()
        state = _make_state()
        i18n = _make_i18n()

        await fsm_per_company_count(message, user, state, i18n)

        state.clear.assert_not_called()
