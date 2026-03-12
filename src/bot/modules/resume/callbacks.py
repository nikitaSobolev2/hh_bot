from aiogram.filters.callback_data import CallbackData


class ResumeCallback(CallbackData, prefix="res"):
    action: str
    summary_id: int = 0
    company_id: int = 0
    work_exp_id: int = 0
    page: int = 0
