from aiogram.filters.callback_data import CallbackData


class VacancySummaryCallback(CallbackData, prefix="vs"):
    action: str
    summary_id: int = 0
    page: int = 0
    step: int = 0
