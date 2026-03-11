from aiogram.filters.callback_data import CallbackData


class InterviewCallback(CallbackData, prefix="iv"):
    action: str
    interview_id: int = 0
    improvement_id: int = 0
    page: int = 0


class InterviewFormCallback(CallbackData, prefix="ivf"):
    action: str
    value: str = ""
