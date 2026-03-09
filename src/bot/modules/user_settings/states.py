from aiogram.fsm.state import State, StatesGroup


class UserSettingsForm(StatesGroup):
    timezone = State()
