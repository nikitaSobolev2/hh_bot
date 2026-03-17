"""Callback data for cover letter module."""

from aiogram.filters.callback_data import CallbackData


class CoverLetterCallback(CallbackData, prefix="cl"):
    action: str
    task_id: int = 0
    vacancy_id: int = 0
    source: str = ""
    page: int = 0
