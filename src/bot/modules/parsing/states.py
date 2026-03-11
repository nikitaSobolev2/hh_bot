from aiogram.fsm.state import State, StatesGroup


class ParsingForm(StatesGroup):
    vacancy_title = State()
    search_url = State()
    keyword_filter = State()
    target_count = State()
    compat_check = State()
    compat_threshold = State()
    blacklist_check = State()
    confirm = State()
    retry_count = State()
    retry_compat_check = State()
    retry_compat_threshold = State()
    key_phrases_count = State()
    work_exp_company_name = State()
    work_exp_stack = State()
    key_phrases_per_company_count = State()
