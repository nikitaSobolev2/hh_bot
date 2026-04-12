from aiogram.fsm.state import State, StatesGroup


class EmployerQuestionFlow(StatesGroup):
    """User sends employer question text for AI answer (per interview)."""

    awaiting_question = State()
    awaiting_answer_edit = State()


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
    notes_noting = State()
    notes_edit_await_number = State()
    notes_edit_await_text = State()
    notes_delete_await_number = State()
