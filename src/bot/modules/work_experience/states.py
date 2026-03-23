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

    # Generate achievements/duties from pasted reference text (menu or detail)
    ref_text_pick_company = State()
    ref_text_paste = State()

    # Improve tech stack (menu path: pick company)
    improve_stack_pick_company = State()
