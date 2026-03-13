"""Limit helpers for admin vs user separation.

Admins bypass all form limits; regular users are subject to configured caps.
"""

from __future__ import annotations

from src.models.user import User

# User limits
MAX_TARGET_COUNT_USER = 50
MAX_PER_COMPANY_COUNT_USER = 8
MAX_KEY_PHRASES_COUNT_USER = 30
MAX_WORK_EXPERIENCES_USER = 6
MAX_COMPANY_NAME_LENGTH_USER = 255
MAX_TITLE_LENGTH_USER = 255
MAX_MESSAGE_LENGTH_USER = 4000
MAX_MESSAGE_LENGTH_RESUME_USER = 3800
COMPAT_THRESHOLD_MIN_USER = 1
COMPAT_THRESHOLD_MAX_USER = 100
MIN_COMPAT_MIN_USER = 0
MIN_COMPAT_MAX_USER = 100

# Admin limits (effectively unlimited or Telegram max)
MAX_TARGET_COUNT_ADMIN = 9999
MAX_PER_COMPANY_COUNT_ADMIN = 999
MAX_KEY_PHRASES_COUNT_ADMIN = 999
MAX_WORK_EXPERIENCES_ADMIN = 999
MAX_COMPANY_NAME_LENGTH_ADMIN = 4096
MAX_TITLE_LENGTH_ADMIN = 4096
MAX_MESSAGE_LENGTH_ADMIN = 4096
MIN_COMPAT_MAX_ADMIN = 999


def get_max_target_count(user: User) -> int:
    return MAX_TARGET_COUNT_ADMIN if user.is_admin else MAX_TARGET_COUNT_USER


def get_max_per_company_count(user: User) -> int:
    return MAX_PER_COMPANY_COUNT_ADMIN if user.is_admin else MAX_PER_COMPANY_COUNT_USER


def get_max_key_phrases_count(user: User) -> int:
    return MAX_KEY_PHRASES_COUNT_ADMIN if user.is_admin else MAX_KEY_PHRASES_COUNT_USER


def get_max_work_experiences(user: User) -> int:
    return MAX_WORK_EXPERIENCES_ADMIN if user.is_admin else MAX_WORK_EXPERIENCES_USER


def get_max_text_length(user: User, field: str) -> int:
    if user.is_admin:
        return MAX_COMPANY_NAME_LENGTH_ADMIN if field == "company_name" else MAX_TITLE_LENGTH_ADMIN
    return MAX_COMPANY_NAME_LENGTH_USER if field == "company_name" else MAX_TITLE_LENGTH_USER


def get_max_message_length(user: User, context: str = "default") -> int:
    if user.is_admin:
        return MAX_MESSAGE_LENGTH_ADMIN
    return MAX_MESSAGE_LENGTH_RESUME_USER if context == "resume" else MAX_MESSAGE_LENGTH_USER


def get_compat_range(user: User) -> tuple[int, int]:
    if user.is_admin:
        return (0, COMPAT_THRESHOLD_MAX_USER)
    return (COMPAT_THRESHOLD_MIN_USER, COMPAT_THRESHOLD_MAX_USER)


def get_min_compat_range(user: User) -> tuple[int, int]:
    if user.is_admin:
        return (MIN_COMPAT_MIN_USER, MIN_COMPAT_MAX_ADMIN)
    return (MIN_COMPAT_MIN_USER, MIN_COMPAT_MAX_USER)
