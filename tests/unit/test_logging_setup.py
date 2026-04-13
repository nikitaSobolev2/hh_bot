"""Tests for logging setup fallbacks."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch


def _reset_logging_module():
    import src.core.logging as logging_module

    logging_module = importlib.reload(logging_module)
    for handler in logging.getLogger().handlers[:]:
        logging.getLogger().removeHandler(handler)
    return logging_module


def test_setup_logging_falls_back_to_console_when_file_handler_is_unwritable() -> None:
    logging_module = _reset_logging_module()

    with (
        patch.object(logging_module.settings, "log_dir", Path("/app/logs")),
        patch.object(logging_module.settings, "log_level", "INFO"),
        patch.object(logging_module.settings, "bot_token", "token"),
        patch.object(logging_module.settings, "log_telegram_chat_id", ""),
        patch.object(
            logging,
            "FileHandler",
            side_effect=PermissionError(13, "Permission denied", "/app/logs/hh_bot.log"),
        ),
        patch("builtins.print") as print_mock,
    ):
        logging_module.setup_logging()

    assert any(handler.__class__.__name__ == "RichHandler" for handler in logging.getLogger().handlers)
    assert not any(
        handler.__class__.__name__ == "FileHandler"
        for handler in logging.getLogger().handlers
    )
    print_mock.assert_called_once()
