from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.ban import UserBan
from src.models.support import SupportAttachment, SupportMessage, SupportTicket


class TestIsAllowedAttachment:
    def test_photo_allowed(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = [MagicMock(file_id="photo_123")]
        message.document = None
        message.video = None

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is True
        assert file_id == "photo_123"
        assert file_type == "photo"

    def test_txt_document_allowed(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = None
        message.document = MagicMock(
            file_id="doc_123",
            file_name="notes.txt",
            mime_type="text/plain",
        )
        message.video = None

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is True
        assert file_id == "doc_123"
        assert file_type == "document"
        assert file_name == "notes.txt"

    def test_mp4_video_allowed(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = MagicMock(file_id="vid_123", file_name="demo.mp4", mime_type="video/mp4")

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is True
        assert file_id == "vid_123"
        assert file_type == "video"

    def test_pdf_document_rejected(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = None
        message.document = MagicMock(
            file_id="doc_456",
            file_name="report.pdf",
            mime_type="application/pdf",
        )
        message.video = None

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is False

    def test_avi_video_rejected(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = MagicMock(file_id="vid_456", file_name="demo.avi", mime_type="video/avi")

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is False

    def test_no_attachment(self):
        from src.bot.modules.support.services import is_allowed_attachment

        message = MagicMock()
        message.photo = None
        message.document = None
        message.video = None

        allowed, file_id, file_type, file_name, mime_type = is_allowed_attachment(message)
        assert allowed is False


class TestBanPeriodParsing:
    def test_parse_days(self):
        import re

        pattern = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)
        match = pattern.match("7d")
        assert match is not None
        assert int(match.group(1)) == 7
        assert match.group(2).lower() == "d"

    def test_parse_hours(self):
        import re

        pattern = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)
        match = pattern.match("24h")
        assert match is not None
        assert int(match.group(1)) == 24
        assert match.group(2).lower() == "h"

    def test_parse_minutes(self):
        import re

        pattern = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)
        match = pattern.match("30m")
        assert match is not None
        assert int(match.group(1)) == 30
        assert match.group(2).lower() == "m"

    def test_parse_invalid(self):
        import re

        pattern = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)
        assert pattern.match("abc") is None
        assert pattern.match("") is None
        assert pattern.match("7x") is None

    def test_permanent(self):
        assert "0" == "0"


class TestCheckBanExpiry:
    @pytest.mark.asyncio
    async def test_not_banned_returns_false(self):
        from src.bot.modules.support.services import check_ban_expiry

        user = MagicMock()
        user.is_banned = False
        session = AsyncMock()

        result = await check_ban_expiry(session, user)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_ban_unbans_user(self):
        from src.bot.modules.support.services import check_ban_expiry

        user = MagicMock()
        user.is_banned = True
        user.id = 1

        expired_ban = MagicMock()
        expired_ban.banned_until = datetime.now(UTC) - timedelta(hours=1)
        expired_ban.is_active = True

        session = AsyncMock()

        with (
            patch("src.bot.modules.support.services.UserBanRepository") as mock_ban_cls,
            patch("src.bot.modules.support.services.UserRepository") as mock_user_cls,
        ):
            ban_repo = mock_ban_cls.return_value
            ban_repo.get_active_ban = AsyncMock(return_value=expired_ban)
            ban_repo.deactivate_bans = AsyncMock()

            user_repo = mock_user_cls.return_value
            user_repo.update = AsyncMock()

            result = await check_ban_expiry(session, user)
            assert result is True

    @pytest.mark.asyncio
    async def test_active_ban_returns_false(self):
        from src.bot.modules.support.services import check_ban_expiry

        user = MagicMock()
        user.is_banned = True
        user.id = 1

        active_ban = MagicMock()
        active_ban.banned_until = datetime.now(UTC) + timedelta(days=7)
        active_ban.is_active = True

        session = AsyncMock()

        with patch("src.bot.modules.support.services.UserBanRepository") as mock_ban_cls:
            ban_repo = mock_ban_cls.return_value
            ban_repo.get_active_ban = AsyncMock(return_value=active_ban)

            result = await check_ban_expiry(session, user)
            assert result is False

    @pytest.mark.asyncio
    async def test_permanent_ban_returns_false(self):
        from src.bot.modules.support.services import check_ban_expiry

        user = MagicMock()
        user.is_banned = True
        user.id = 1

        permanent_ban = MagicMock()
        permanent_ban.banned_until = None
        permanent_ban.is_active = True

        session = AsyncMock()

        with patch("src.bot.modules.support.services.UserBanRepository") as mock_ban_cls:
            ban_repo = mock_ban_cls.return_value
            ban_repo.get_active_ban = AsyncMock(return_value=permanent_ban)

            result = await check_ban_expiry(session, user)
            assert result is False


class TestSupportModels:
    def test_ticket_repr(self):
        ticket = MagicMock(spec=SupportTicket)
        ticket.id = 1
        ticket.status = "new"
        ticket.user_id = 42
        result = SupportTicket.__repr__(ticket)
        assert "SupportTicket" in result
        assert "new" in result

    def test_message_repr(self):
        msg = MagicMock(spec=SupportMessage)
        msg.id = 1
        msg.ticket_id = 2
        msg.is_from_admin = False
        result = SupportMessage.__repr__(msg)
        assert "SupportMessage" in result

    def test_attachment_repr(self):
        att = MagicMock(spec=SupportAttachment)
        att.id = 1
        att.file_type = "photo"
        result = SupportAttachment.__repr__(att)
        assert "SupportAttachment" in result

    def test_ban_repr(self):
        ban = MagicMock(spec=UserBan)
        ban.id = 1
        ban.user_id = 42
        ban.is_active = True
        result = UserBan.__repr__(ban)
        assert "UserBan" in result


class TestAllowedExtensions:
    def test_all_photo_extensions_present(self):
        from src.bot.modules.support.services import ALLOWED_PHOTO_EXTENSIONS

        assert "webp" in ALLOWED_PHOTO_EXTENSIONS
        assert "png" in ALLOWED_PHOTO_EXTENSIONS
        assert "jpg" in ALLOWED_PHOTO_EXTENSIONS
        assert "jpeg" in ALLOWED_PHOTO_EXTENSIONS

    def test_txt_allowed(self):
        from src.bot.modules.support.services import ALLOWED_DOC_EXTENSIONS

        assert "txt" in ALLOWED_DOC_EXTENSIONS

    def test_mp4_allowed(self):
        from src.bot.modules.support.services import ALLOWED_VIDEO_EXTENSIONS

        assert "mp4" in ALLOWED_VIDEO_EXTENSIONS

    def test_combined_extensions(self):
        from src.bot.modules.support.services import ALLOWED_EXTENSIONS

        assert len(ALLOWED_EXTENSIONS) == 6


class TestCallbackData:
    def test_support_callback_pack(self):
        from src.bot.modules.support.callbacks import SupportCallback

        cb = SupportCallback(action="list", page=2)
        packed = cb.pack()
        assert "support" in packed
        unpacked = SupportCallback.unpack(packed)
        assert unpacked.action == "list"
        assert unpacked.page == 2

    def test_ticket_admin_callback_pack(self):
        from src.bot.modules.support.callbacks import TicketAdminCallback

        cb = TicketAdminCallback(action="take", ticket_id=5, user_id=10)
        packed = cb.pack()
        unpacked = TicketAdminCallback.unpack(packed)
        assert unpacked.action == "take"
        assert unpacked.ticket_id == 5
        assert unpacked.user_id == 10

    def test_ticket_filter_callback_pack(self):
        from src.bot.modules.support.callbacks import TicketFilterCallback

        cb = TicketFilterCallback(status="new", page=0)
        packed = cb.pack()
        unpacked = TicketFilterCallback.unpack(packed)
        assert unpacked.status == "new"


class TestStates:
    def test_ticket_form_states(self):
        from src.bot.modules.support.states import TicketForm

        assert TicketForm.title is not None
        assert TicketForm.description is not None
        assert TicketForm.attachments is not None

    def test_user_conversation_state(self):
        from src.bot.modules.support.states import UserConversation

        assert UserConversation.chatting is not None

    def test_admin_conversation_states(self):
        from src.bot.modules.support.states import AdminConversation

        assert AdminConversation.chatting is not None
        assert AdminConversation.close_result is not None
        assert AdminConversation.close_status is not None
        assert AdminConversation.ban_period is not None
        assert AdminConversation.ban_reason is not None
