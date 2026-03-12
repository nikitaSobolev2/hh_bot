from aiogram.fsm.state import State, StatesGroup


class WorkExpForm(StatesGroup):
    company_name = State()
    stack = State()
