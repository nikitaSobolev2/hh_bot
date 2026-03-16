"""FSM states for Interview Q&A module."""

from aiogram.fsm.state import State, StatesGroup


class InterviewQAForm(StatesGroup):
    """States for interview QA flows."""

    why_reason_manual = State()
    custom_question_await = State()
