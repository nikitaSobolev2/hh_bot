from aiogram.fsm.state import State, StatesGroup


class InterviewForm(StatesGroup):
    source_choice = State()
    hh_link = State()
    vacancy_title = State()
    vacancy_description = State()
    company_name = State()
    experience_level = State()
    adding_question = State()
    adding_answer = State()
    user_improvement_notes = State()
    confirm = State()
