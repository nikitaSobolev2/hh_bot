from aiogram.fsm.state import State, StatesGroup


class HhAccountRenameForm(StatesGroup):
    waiting_label = State()


class HhBrowserImportForm(StatesGroup):
    waiting_json = State()
