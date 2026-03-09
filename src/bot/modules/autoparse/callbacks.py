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
