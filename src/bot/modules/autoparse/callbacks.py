from aiogram.filters.callback_data import CallbackData


class AutoparseCallback(CallbackData, prefix="ap"):
    action: str
    company_id: int = 0
    page: int = 0
    aux_id: int = 0


class AutoparseDownloadCallback(CallbackData, prefix="apd"):
    company_id: int
    format: str


class AutoparseSettingsCallback(CallbackData, prefix="aps"):
    action: str


class AutoparseWorkExpCallback(CallbackData, prefix="apwe"):
    action: str
    work_exp_id: int = 0


class FeedCallback(CallbackData, prefix="feed"):
    # start | like | dislike | stop | toggle_view | create_cover_letter |
    # regenerate_cover_letter | back_to_vacancy | pick_hh_account | respond | respond_ai_cover |
    # respond_pick | respond_refresh_resumes | respond_cancel | respond_letter_generate |
    # respond_letter_skip
    action: str
    session_id: int
    vacancy_id: int = 0
    mode: str = "summary"  # summary | description
    hh_account_id: int = 0
    resume_idx: int = 0
