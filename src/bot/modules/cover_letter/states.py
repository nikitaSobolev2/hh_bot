"""FSM states for cover letter module."""

from aiogram.fsm.state import State, StatesGroup


class CoverLetterForm(StatesGroup):
    waiting_url = State()
