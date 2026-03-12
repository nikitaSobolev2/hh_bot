from aiogram.filters.callback_data import CallbackData


class WorkExpCallback(CallbackData, prefix="we"):
    action: str
    work_exp_id: int = 0
    return_to: str = "menu"
