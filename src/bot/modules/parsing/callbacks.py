from aiogram.filters.callback_data import CallbackData


class ParsingCallback(CallbackData, prefix="parsing"):
    action: str
    company_id: int = 0
    page: int = 0


class FormatCallback(CallbackData, prefix="fmt"):
    company_id: int
    format: str


class KeyPhrasesCallback(CallbackData, prefix="kp"):
    company_id: int
    action: str
    style: str = ""
    count: int = 0
    lang: str = ""
    mode: str = ""


class WorkExperienceCallback(CallbackData, prefix="we"):
    action: str
    company_id: int = 0
    work_exp_id: int = 0
