from aiogram.fsm.state import State, StatesGroup


class ResumeForm(StatesGroup):
    collecting_summary_info = State()
    waiting_for_keyphrases = State()
    entering_keywords = State()
