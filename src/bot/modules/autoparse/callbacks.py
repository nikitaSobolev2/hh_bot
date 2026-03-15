from aiogram.filters.callback_data import CallbackData


class AutoparseCallback(CallbackData, prefix="ap"):
    action: str
    company_id: int = 0
    page: int = 0


class AutoparseDownloadCallback(CallbackData, prefix="apd"):
    company_id: int
    format: str


class AutoparseSettingsCallback(CallbackData, prefix="aps"):
    action: str


class AutoparseWorkExpCallback(CallbackData, prefix="apwe"):
    action: str
    work_exp_id: int = 0


class FeedCallback(CallbackData, prefix="feed"):
    # start | like | dislike | stop | toggle_view | create_cover_letter | back_to_vacancy
    action: str
    session_id: int
    vacancy_id: int = 0
    mode: str = "summary"  # summary | description
