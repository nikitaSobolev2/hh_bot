from aiogram.filters.callback_data import CallbackData


class HhAccountCallback(CallbackData, prefix="hha"):
    action: str  # menu | add | remove | rename | cancel_rename | cancel_browser | remote_login | cancel_login_assist | download_storage | check_session | replace_session
    account_id: int = 0
