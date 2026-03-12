from aiogram.fsm.state import State, StatesGroup


class AchievementForm(StatesGroup):
    collecting_achievements = State()
    collecting_responsibilities = State()
