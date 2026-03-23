from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class ImproveStackAction(StrEnum):
    pick = "pick"
    menu_cancel = "menu_cancel"
    from_edit = "from_edit"


class ImproveStackCallback(CallbackData, prefix="we_improve_stack"):
    action: ImproveStackAction
    work_exp_id: int = 0
    return_to: str = "menu"


class WorkExpCallback(CallbackData, prefix="we"):
    action: str
    work_exp_id: int = 0
    return_to: str = "menu"
    field: str = ""
