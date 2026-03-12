from aiogram.filters.callback_data import CallbackData


class ResumeCallback(CallbackData, prefix="res"):
    action: str
    summary_id: int = 0
