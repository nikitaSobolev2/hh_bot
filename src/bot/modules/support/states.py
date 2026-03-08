from aiogram.fsm.state import State, StatesGroup


class TicketForm(StatesGroup):
    title = State()
    description = State()
    attachments = State()


class UserConversation(StatesGroup):
    chatting = State()


class AdminConversation(StatesGroup):
    chatting = State()
    close_result = State()
    close_status = State()
    ban_period = State()
    ban_reason = State()


class AdminTicketSearch(StatesGroup):
    waiting_query = State()
