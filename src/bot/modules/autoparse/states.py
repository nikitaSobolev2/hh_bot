from aiogram.fsm.state import State, StatesGroup


class AutoparseForm(StatesGroup):
    select_template = State()
    vacancy_title = State()
    search_url = State()
    keyword_filter = State()
    skills = State()


class AutoparseSettingsForm(StatesGroup):
    work_experience = State()
    send_time = State()
    tech_stack = State()
