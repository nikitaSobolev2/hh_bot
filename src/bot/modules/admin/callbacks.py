from aiogram.filters.callback_data import CallbackData


class AdminCallback(CallbackData, prefix="admin"):
    action: str
    value: str = ""


class AdminUserCallback(CallbackData, prefix="adm_user"):
    action: str
    user_id: int = 0
    page: int = 0


class AdminSettingCallback(CallbackData, prefix="adm_set"):
    action: str
    key: str = ""
    value: str = ""
