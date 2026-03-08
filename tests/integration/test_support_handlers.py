from unittest.mock import MagicMock

import pytest

from src.bot.modules.support.keyboards import (
    admin_conversation_keyboard,
    admin_inbox_keyboard,
    close_status_keyboard,
    skip_attachments_keyboard,
    ticket_channel_keyboard,
    ticket_detail_keyboard,
    user_conversation_keyboard,
    user_ticket_list_keyboard,
)
from src.models.support import SupportTicket


@pytest.fixture
def mock_i18n():
    i18n = MagicMock()
    i18n.get = MagicMock(side_effect=lambda key, **kwargs: f"[{key}]")
    return i18n


def _make_ticket(**overrides):
    defaults = {
        "id": 1,
        "user_id": 42,
        "admin_id": None,
        "title": "Test Ticket",
        "description": "Test description",
        "status": "new",
        "close_result": None,
        "close_status": None,
        "channel_message_id": None,
        "admin": None,
    }
    defaults.update(overrides)
    ticket = MagicMock(spec=SupportTicket)
    for k, v in defaults.items():
        setattr(ticket, k, v)
    return ticket


@pytest.fixture
def sample_ticket():
    return _make_ticket()


@pytest.fixture
def sample_ticket_in_progress():
    admin = MagicMock()
    admin.username = "admin_user"
    admin.first_name = "Admin"
    return _make_ticket(status="in_progress", admin_id=100, admin=admin)


@pytest.fixture
def sample_ticket_closed():
    return _make_ticket(status="closed", close_result="Fixed", close_status="valid")


class TestUserTicketListKeyboard:
    def test_empty_list(self, mock_i18n):
        kb = user_ticket_list_keyboard([], 0, False, mock_i18n)
        buttons = kb.inline_keyboard
        assert len(buttons) >= 2
        assert any("[btn-new-ticket]" in b.text for row in buttons for b in row)
        assert any("[btn-back-menu]" in b.text for row in buttons for b in row)

    def test_with_tickets(self, mock_i18n, sample_ticket):
        kb = user_ticket_list_keyboard([sample_ticket], 0, False, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("Test Ticket" in b.text for row in buttons for b in row)

    def test_unseen_marker(self, mock_i18n, sample_ticket):
        kb = user_ticket_list_keyboard(
            [sample_ticket],
            0,
            False,
            mock_i18n,
            unseen_ticket_ids={1},
        )
        buttons = kb.inline_keyboard
        ticket_row = [b for row in buttons for b in row if "Test Ticket" in b.text]
        assert len(ticket_row) == 1
        assert "💬" in ticket_row[0].text

    def test_pagination(self, mock_i18n, sample_ticket):
        kb = user_ticket_list_keyboard([sample_ticket], 0, True, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-next]" in b.text for row in buttons for b in row)

    def test_page_2_has_prev(self, mock_i18n, sample_ticket):
        kb = user_ticket_list_keyboard([sample_ticket], 1, False, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-prev]" in b.text for row in buttons for b in row)


class TestTicketDetailKeyboard:
    def test_open_ticket_has_enter_button(self, mock_i18n, sample_ticket):
        kb = ticket_detail_keyboard(sample_ticket, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-enter-conversation]" in b.text for row in buttons for b in row)

    def test_closed_ticket_no_enter_button(self, mock_i18n, sample_ticket_closed):
        kb = ticket_detail_keyboard(sample_ticket_closed, mock_i18n)
        buttons = kb.inline_keyboard
        assert not any("[btn-enter-conversation]" in b.text for row in buttons for b in row)

    def test_has_back_button(self, mock_i18n, sample_ticket):
        kb = ticket_detail_keyboard(sample_ticket, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-back-tickets]" in b.text for row in buttons for b in row)


class TestSkipAttachmentsKeyboard:
    def test_has_skip_and_done(self, mock_i18n):
        kb = skip_attachments_keyboard(mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-skip-attachments]" in b.text for row in buttons for b in row)
        assert any("[btn-done-attachments]" in b.text for row in buttons for b in row)


class TestUserConversationKeyboard:
    def test_has_quit_and_close(self, mock_i18n):
        kb = user_conversation_keyboard(mock_i18n)
        buttons = kb.keyboard
        all_texts = [b.text for row in buttons for b in row]
        assert "[btn-quit-conversation]" in all_texts
        assert "[btn-close-ticket]" in all_texts

    def test_is_resize(self, mock_i18n):
        kb = user_conversation_keyboard(mock_i18n)
        assert kb.resize_keyboard is True


class TestTicketChannelKeyboard:
    def test_has_take_button(self, mock_i18n, sample_ticket):
        kb = ticket_channel_keyboard(sample_ticket, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-take-into-work]" in b.text for row in buttons for b in row)

    def test_has_all_action_buttons(self, mock_i18n, sample_ticket):
        kb = ticket_channel_keyboard(sample_ticket, mock_i18n)
        all_texts = [b.text for row in kb.inline_keyboard for b in row]
        expected = [
            "[btn-take-into-work]",
            "[btn-view-profile]",
            "[btn-check-companies]",
            "[btn-check-tickets]",
            "[btn-check-notifications]",
            "[btn-ban]",
            "[btn-close-ticket-admin]",
        ]
        for exp in expected:
            assert exp in all_texts, f"Missing button: {exp}"


class TestAdminInboxKeyboard:
    def test_empty_inbox(self, mock_i18n):
        kb = admin_inbox_keyboard([], 0, False, mock_i18n)
        buttons = kb.inline_keyboard
        assert any("[btn-search]" in b.text for row in buttons for b in row)

    def test_with_tickets_and_filter(self, mock_i18n, sample_ticket):
        kb = admin_inbox_keyboard(
            [sample_ticket],
            0,
            False,
            mock_i18n,
            current_filter="new",
        )
        buttons = kb.inline_keyboard
        filter_row = [b for row in buttons for b in row if "[btn-filter-" in b.text]
        assert len(filter_row) == 4
        active_filter = [b for b in filter_row if "▪️" in b.text]
        assert len(active_filter) == 1

    def test_unseen_marker_in_inbox(self, mock_i18n, sample_ticket):
        kb = admin_inbox_keyboard(
            [sample_ticket],
            0,
            False,
            mock_i18n,
            unseen_ticket_ids={1},
        )
        ticket_btns = [b for row in kb.inline_keyboard for b in row if "Test Ticket" in b.text]
        assert len(ticket_btns) == 1
        assert "💬" in ticket_btns[0].text


class TestAdminConversationKeyboard:
    def test_has_all_buttons(self, mock_i18n):
        kb = admin_conversation_keyboard(mock_i18n)
        all_texts = [b.text for row in kb.keyboard for b in row]
        expected = [
            "[btn-quit-conversation]",
            "[btn-close-ticket-admin]",
            "[btn-view-profile]",
            "[btn-check-companies]",
            "[btn-check-tickets]",
            "[btn-check-notifications]",
            "[btn-ban]",
            "[btn-message-history]",
        ]
        for exp in expected:
            assert exp in all_texts, f"Missing button: {exp}"


class TestCloseStatusKeyboard:
    def test_has_three_statuses_and_cancel(self, mock_i18n):
        kb = close_status_keyboard(mock_i18n)
        buttons = kb.inline_keyboard
        assert len(buttons) == 4
        all_texts = [b.text for row in buttons for b in row]
        assert "[btn-status-valid]" in all_texts
        assert "[btn-status-invalid]" in all_texts
        assert "[btn-status-bug]" in all_texts
        assert "[btn-cancel]" in all_texts


class TestAdminTicketDetailKeyboard:
    def test_new_ticket_has_take_button(self, mock_i18n, sample_ticket):
        from src.bot.modules.support.keyboards import admin_ticket_detail_keyboard

        kb = admin_ticket_detail_keyboard(sample_ticket, mock_i18n)
        all_texts = [b.text for row in kb.inline_keyboard for b in row]
        assert "[btn-take-into-work]" in all_texts

    def test_in_progress_has_enter_button(self, mock_i18n, sample_ticket_in_progress):
        from src.bot.modules.support.keyboards import admin_ticket_detail_keyboard

        kb = admin_ticket_detail_keyboard(sample_ticket_in_progress, mock_i18n)
        all_texts = [b.text for row in kb.inline_keyboard for b in row]
        assert "[btn-enter-conversation]" in all_texts

    def test_closed_ticket_no_action_buttons(self, mock_i18n, sample_ticket_closed):
        from src.bot.modules.support.keyboards import admin_ticket_detail_keyboard

        kb = admin_ticket_detail_keyboard(sample_ticket_closed, mock_i18n)
        all_texts = [b.text for row in kb.inline_keyboard for b in row]
        assert "[btn-take-into-work]" not in all_texts
        assert "[btn-enter-conversation]" not in all_texts
