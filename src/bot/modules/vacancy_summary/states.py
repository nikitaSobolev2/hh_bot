from aiogram.fsm.state import State, StatesGroup


class VacancySummaryForm(StatesGroup):
    excluded_industries = State()
    location = State()
    remote_preference = State()
    additional_notes = State()
