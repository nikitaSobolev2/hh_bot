from aiogram.fsm.state import State, StatesGroup


class ParsingForm(StatesGroup):
    vacancy_title = State()
    search_url = State()
    keyword_filter = State()
    target_count = State()
    blacklist_check = State()
    confirm = State()
