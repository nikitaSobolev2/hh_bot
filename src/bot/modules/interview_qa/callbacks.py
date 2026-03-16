from aiogram.filters.callback_data import CallbackData


class InterviewQACallback(CallbackData, prefix="iqa"):
    action: str
    question_key: str = ""
    reason: str = ""
    interview_id: int = 0
    page: int = 0
