from aiogram.fsm.state import State, StatesGroup


class ParsingForm(StatesGroup):
    vacancy_title = State()
    search_url = State()
    keyword_filter = State()
    target_count = State()
    blacklist_check = State()
    confirm = State()
    retry_count = State()
    key_phrases_count = State()
    work_exp_company_name = State()
    work_exp_stack = State()
    key_phrases_per_company_count = State()
