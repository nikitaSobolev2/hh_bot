from aiogram.filters.callback_data import CallbackData


class AchievementCallback(CallbackData, prefix="ach"):
    action: str
    generation_id: int = 0
    item_id: int = 0
    work_exp_id: int = 0
    page: int = 0
