"""Tests for runtime settings sync from DB-managed values."""

from src.config import settings, sync_setting_to_runtime


def test_sync_setting_to_runtime_preserves_bool_task_autorespond() -> None:
    """Booleans must not be stringified (e.g. False -> the string 'False', which is truthy)."""
    original = settings.task_autorespond_enabled
    try:
        sync_setting_to_runtime("task_autorespond_enabled", False)
        assert settings.task_autorespond_enabled is False
        assert isinstance(settings.task_autorespond_enabled, bool)

        sync_setting_to_runtime("task_autorespond_enabled", True)
        assert settings.task_autorespond_enabled is True
        assert isinstance(settings.task_autorespond_enabled, bool)
    finally:
        settings.task_autorespond_enabled = original
