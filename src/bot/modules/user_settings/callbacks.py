from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="settings"):
    action: str
    value: str = ""


class BlacklistCallback(CallbackData, prefix="bl"):
    action: str
    context: str = ""


class TimezoneCallback(CallbackData, prefix="tz"):
    action: str  # "page", "select", "search"
    page: int = 0
    value: str = ""
