from aiogram.filters.callback_data import CallbackData


class MenuCallback(CallbackData, prefix="menu"):
    action: str
