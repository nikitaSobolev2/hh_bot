from aiogram.filters.callback_data import CallbackData


class InterviewQACallback(CallbackData, prefix="iqa"):
    action: str
    question_key: str = ""
    reason: str = ""
