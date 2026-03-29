from aiogram.filters.callback_data import CallbackData


class TaskGroupCallback(CallbackData, prefix="tgrp"):
    """Configure task group steps (add company per kind, remove line)."""

    action: str
    kind: str = ""
    company_id: int = 0
    index: int = -1
