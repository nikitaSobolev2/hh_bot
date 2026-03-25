"""Structured outcomes for Playwright-based HH.ru UI flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ApplyOutcome(StrEnum):
    SUCCESS = "success"
    ALREADY_RESPONDED = "already_responded"
    EMPLOYER_QUESTIONS = "employer_questions"
    NO_APPLY_BUTTON = "no_apply_button"
    CAPTCHA = "captcha"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMITED = "rate_limited"
    VACANCY_UNAVAILABLE = "vacancy_unavailable"
    ERROR = "error"


@dataclass
class ResumeOption:
    id: str
    title: str


@dataclass
class ApplyResult:
    outcome: ApplyOutcome
    detail: str | None = None
    screenshot_bytes: bytes | None = None


@dataclass
class ListResumesResult:
    resumes: list[ResumeOption]
    outcome: ApplyOutcome
    detail: str | None = None
    screenshot_bytes: bytes | None = None
