from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="settings"):
    action: str
    value: str = ""


class BlacklistCallback(CallbackData, prefix="bl"):
    action: str
    context: str = ""
