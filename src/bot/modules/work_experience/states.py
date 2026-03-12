from aiogram.fsm.state import State, StatesGroup


class WorkExpForm(StatesGroup):
    # Creation steps
    company_name = State()
    title = State()
    period = State()
    stack = State()
    achievements = State()
    duties = State()

    # Single-field edit step
    edit_value = State()
    edit_achievements = State()
    edit_duties = State()
