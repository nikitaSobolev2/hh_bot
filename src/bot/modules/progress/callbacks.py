"""Callback data for progress bar actions."""

from aiogram.filters.callback_data import CallbackData


class ProgressCallback(CallbackData, prefix="prog"):
    """Callback for progress bar actions (e.g. cancel task)."""

    action: str
    task_key: str
