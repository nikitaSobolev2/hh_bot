"""Unit tests for work experience repository and keyboard builders."""

from unittest.mock import MagicMock

import pytest

from src.bot.modules.parsing.callbacks import WorkExperienceCallback
from src.bot.modules.parsing.keyboards import (
    MAX_WORK_EXPERIENCES,
    cancel_add_company_keyboard,
    per_company_count_keyboard,
    work_experience_keyboard,
)
from src.models.work_experience import UserWorkExperience
from src.repositories.work_experience import WorkExperienceRepository


def _make_experience(exp_id: int, name: str, stack: str, *, active: bool = True) -> MagicMock:
    exp = MagicMock(spec=UserWorkExperience)
    exp.id = exp_id
    exp.company_name = name
    exp.stack = stack
    exp.is_active = active
    return exp


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.get = MagicMock(side_effect=lambda key, **kw: key)
    return i18n


class TestWorkExperienceRepository:
    @pytest.mark.asyncio
    async def test_get_active_by_user_calls_execute(self, mock_session):
        repo = WorkExperienceRepository(mock_session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repo.get_active_by_user(1)

        mock_session.execute.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_count_active_by_user_returns_int(self, mock_session):
        repo = WorkExperienceRepository(mock_session)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        mock_session.execute.return_value = mock_result

        count = await repo.count_active_by_user(1)

        assert count == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_sets_is_active_false(self, mock_session):
        repo = WorkExperienceRepository(mock_session)
        entity = MagicMock(spec=UserWorkExperience)
        entity.is_active = True
        entity.user_id = 1
        mock_session.get.return_value = entity

        result = await repo.deactivate(42, user_id=1)

        assert result is True
        assert entity.is_active is False
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_nonexistent_does_nothing(self, mock_session):
        repo = WorkExperienceRepository(mock_session)
        mock_session.get.return_value = None

        result = await repo.deactivate(999, user_id=1)

        assert result is False
        mock_session.flush.assert_not_called()


class TestWorkExperienceKeyboard:
    def test_empty_experiences_shows_add_and_skip_no_continue(self):
        i18n = _make_i18n()
        kb = work_experience_keyboard(company_id=1, experiences=[], i18n=i18n)

        buttons = [btn for row in kb.inline_keyboard for btn in row]
        texts = [b.text for b in buttons]

        assert any("btn-add-company" in t for t in texts)
        assert any("btn-skip" in t for t in texts)
        assert not any("btn-continue" in t for t in texts)

    def test_with_experiences_shows_remove_add_skip_continue(self):
        i18n = _make_i18n()
        exps = [_make_experience(1, "Acme", "Python, Django")]
        kb = work_experience_keyboard(company_id=10, experiences=exps, i18n=i18n)

        buttons = [btn for row in kb.inline_keyboard for btn in row]
        texts = [b.text for b in buttons]

        assert any("Acme" in t for t in texts)
        assert any("btn-add-company" in t for t in texts)
        assert any("btn-skip" in t for t in texts)
        assert any("btn-continue" in t for t in texts)

    def test_max_experiences_hides_add_button(self):
        i18n = _make_i18n()
        exps = [_make_experience(i, f"Co{i}", f"Stack{i}") for i in range(MAX_WORK_EXPERIENCES)]
        kb = work_experience_keyboard(company_id=1, experiences=exps, i18n=i18n)

        buttons = [btn for row in kb.inline_keyboard for btn in row]
        texts = [b.text for b in buttons]

        assert not any("btn-add-company" in t for t in texts)

    def test_remove_button_callback_contains_work_exp_id(self):
        i18n = _make_i18n()
        exps = [_make_experience(42, "TestCo", "Go")]
        kb = work_experience_keyboard(company_id=5, experiences=exps, i18n=i18n)

        remove_btn = kb.inline_keyboard[0][0]
        parsed = WorkExperienceCallback.unpack(remove_btn.callback_data)

        assert parsed.action == "remove"
        assert parsed.work_exp_id == 42
        assert parsed.company_id == 5


class TestCancelAddCompanyKeyboard:
    def test_has_back_and_cancel_buttons(self):
        i18n = _make_i18n()
        kb = cancel_add_company_keyboard(company_id=1, i18n=i18n)

        assert len(kb.inline_keyboard) == 2
        back_btn = kb.inline_keyboard[0][0]
        cancel_btn = kb.inline_keyboard[1][0]
        for btn in (back_btn, cancel_btn):
            parsed = WorkExperienceCallback.unpack(btn.callback_data)
            assert parsed.action == "cancel_add"
            assert parsed.company_id == 1


class TestPerCompanyCountKeyboard:
    def test_has_back_and_cancel_buttons(self):
        i18n = _make_i18n()
        kb = per_company_count_keyboard(company_id=3, i18n=i18n)

        assert len(kb.inline_keyboard) == 2
        back_btn = kb.inline_keyboard[0][0]
        cancel_btn = kb.inline_keyboard[1][0]
        for btn in (back_btn, cancel_btn):
            parsed = WorkExperienceCallback.unpack(btn.callback_data)
            assert parsed.action == "cancel_add"
            assert parsed.company_id == 3
