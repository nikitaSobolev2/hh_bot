from aiogram.filters.callback_data import CallbackData


class ProfileCallback(CallbackData, prefix="profile"):
    action: str
