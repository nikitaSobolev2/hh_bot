"""Typed callback data for the resume module.

The original ResumeCallback.work_exp_id was overloaded for 3 different
entity types (work experience entries, recommendation letters, and AI draft IDs).
New typed callback classes are introduced below. Handlers should migrate to these
over time. The original class is preserved for backward compatibility.
"""

from aiogram.filters.callback_data import CallbackData


class ResumeCallback(CallbackData, prefix="res"):
    """General resume navigation and actions (maintained for compatibility)."""

    action: str
    summary_id: int = 0
    company_id: int = 0
    work_exp_id: int = 0
    page: int = 0


class ResumeWorkExpCallback(CallbackData, prefix="res_we"):
    """Actions targeting a specific work experience entry."""

    action: str
    work_exp_id: int = 0
    page: int = 0


class ResumeRecLetterCallback(CallbackData, prefix="res_rl"):
    """Actions targeting a specific recommendation letter."""

    action: str
    letter_id: int = 0
    page: int = 0
