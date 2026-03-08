from aiogram.filters.callback_data import CallbackData


class SupportCallback(CallbackData, prefix="support"):
    action: str  # list, new, detail, enter
    ticket_id: int = 0
    page: int = 0


class TicketAdminCallback(CallbackData, prefix="tkt_adm"):
    action: str  # take, close, profile, companies, tickets, notifications, ban
    ticket_id: int = 0
    user_id: int = 0
    page: int = 0


class TicketFilterCallback(CallbackData, prefix="tkt_f"):
    status: str = ""
    page: int = 0


class TicketSearchCallback(CallbackData, prefix="tkt_s"):
    action: str  # prompt, clear
