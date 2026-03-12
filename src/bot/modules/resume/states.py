from aiogram.fsm.state import State, StatesGroup


class ResumeForm(StatesGroup):
    job_title = State()
    skill_level = State()
    entering_keywords = State()
    rec_speaker_name = State()
    rec_speaker_position = State()
    rec_focus = State()
