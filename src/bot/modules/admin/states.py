from aiogram.fsm.state import State, StatesGroup


class AdminSettingForm(StatesGroup):
    waiting_value = State()


class AdminMessageForm(StatesGroup):
    waiting_message = State()


class AdminUserSearchForm(StatesGroup):
    waiting_query = State()


class AdminBalanceForm(StatesGroup):
    waiting_amount = State()
