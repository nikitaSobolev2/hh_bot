from aiogram.fsm.state import State, StatesGroup


class HhAccountRenameForm(StatesGroup):
    waiting_label = State()
