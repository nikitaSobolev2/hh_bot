from aiogram.filters.callback_data import CallbackData


class HhAccountCallback(CallbackData, prefix="hha"):
    action: str  # menu | add | remove | rename | cancel_rename
    account_id: int = 0
