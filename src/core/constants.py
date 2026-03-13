"""Project-wide constants.

All magic strings, numbers, and icon mappings are defined here so they
have a single authoritative source.  Import from this module instead of
scattering literals across handler, keyboard, and service files.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Message length limits (Telegram HTML)
# ---------------------------------------------------------------------------

TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_SAFE_LIMIT = 4000
TELEGRAM_TRUNCATE_LIMIT = 3900
TELEGRAM_CAPTION_LIMIT = 1024


# ---------------------------------------------------------------------------
# Status icons — task/pipeline statuses
# ---------------------------------------------------------------------------

TASK_STATUS_ICONS: dict[str, str] = {
    "pending": "⏳",
    "processing": "🔄",
    "completed": "✅",
    "failed": "❌",
    "disabled": "⏸️",
    "circuit_open": "🚫",
}

SUPPORT_TICKET_STATUS_ICONS: dict[str, str] = {
    "new": "🆕",
    "in_progress": "🔄",
    "closed": "✅",
}

IMPROVEMENT_STATUS_ICONS: dict[str, str] = {
    "pending": "⏳",
    "success": "✅",
    "error": "❌",
}

AUTOPARSE_STATUS_ICONS: dict[str, str] = {
    "enabled": "✅",
    "disabled": "⏸️",
}

PREP_STEP_STATUS_ICONS: dict[str, str] = {
    "pending": "⏳",
    "completed": "✅",
    "in_progress": "🔄",
}


# ---------------------------------------------------------------------------
# Redis key namespaces — each service owns exactly one namespace
# ---------------------------------------------------------------------------


class RedisNamespace(StrEnum):
    CIRCUIT_BREAKER = "cb"
    PROGRESS = "progress"
    CHECKPOINT = "checkpoint"
    LOCK = "lock"
    THROTTLE = "throttle"


# ---------------------------------------------------------------------------
# Redis TTLs (seconds)
# ---------------------------------------------------------------------------

REDIS_PROGRESS_TTL = 4 * 3600  # 4 hours
REDIS_LOCK_TTL = 300  # 5 minutes
REDIS_THROTTLE_TTL = 60  # 1 minute window
REDIS_CB_STATE_TTL = 24 * 3600  # 24 hours
REDIS_CB_FAILURES_TTL = 24 * 3600  # 24 hours
REDIS_CHECKPOINT_TTL = 24 * 3600  # 24 hours
REDIS_MSGLOCK_TTL = 10  # 10 seconds


# ---------------------------------------------------------------------------
# Circuit breaker defaults
# ---------------------------------------------------------------------------

CB_DEFAULT_FAILURE_THRESHOLD = 5
CB_DEFAULT_RECOVERY_TIMEOUT = 60
CB_HALF_OPEN_SUCCESS_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Celery task names — single source of truth
# ---------------------------------------------------------------------------


class TaskName(StrEnum):
    PARSE_COMPANY = "parsing.run_company"
    GENERATE_KEY_PHRASES = "ai.generate_key_phrases"
    AUTOPARSE_DISPATCH = "autoparse.dispatch_all"
    AUTOPARSE_RUN_COMPANY = "autoparse.run_company"
    AUTOPARSE_DELIVER = "autoparse.deliver_feed"
    ANALYZE_INTERVIEW = "interviews.analyze"
    GENERATE_IMPROVEMENT = "interviews.generate_improvement"
    GENERATE_PREP_GUIDE = "interview_prep.generate_guide"
    GENERATE_PREP_DEEP_SUMMARY = "interview_prep.generate_deep_summary"
    GENERATE_PREP_TEST = "interview_prep.generate_test"
    GENERATE_INTERVIEW_QA = "interview_qa.generate"
    GENERATE_VACANCY_SUMMARY = "vacancy_summary.generate"
    GENERATE_ACHIEVEMENTS = "achievements.generate"
    GENERATE_WORK_EXPERIENCE_AI = "work_experience.generate_ai"
    GENERATE_RESUME_KEY_PHRASES = "work_experience.generate_resume_keyphrases"
    GENERATE_RECOMMENDATION_LETTER = "recommendation_letter.generate"


# ---------------------------------------------------------------------------
# App settings keys — all keys used in the app_settings DB table
# ---------------------------------------------------------------------------


class AppSettingKey(StrEnum):
    TASK_PARSING_ENABLED = "task_parsing_enabled"
    TASK_AUTOPARSE_ENABLED = "task_autoparse_enabled"
    TASK_KEYPHRASE_ENABLED = "task_keyphrase_enabled"
    TASK_INTERVIEW_ANALYSIS_ENABLED = "task_interview_analysis_enabled"
    TASK_IMPROVEMENT_FLOW_ENABLED = "task_improvement_flow_enabled"
    TASK_INTERVIEW_PREP_ENABLED = "task_interview_prep_enabled"
    TASK_INTERVIEW_QA_ENABLED = "task_interview_qa_enabled"
    TASK_VACANCY_SUMMARY_ENABLED = "task_vacancy_summary_enabled"
    TASK_ACHIEVEMENTS_ENABLED = "task_achievements_enabled"
    TASK_WORK_EXPERIENCE_AI_ENABLED = "task_work_experience_ai_enabled"
    TASK_RECOMMENDATION_LETTER_ENABLED = "task_recommendation_letter_enabled"

    AUTOPARSE_INTERVAL_HOURS = "autoparse_interval_hours"
    BLACKLIST_DAYS = "blacklist_days"

    CB_PARSING_FAILURE_THRESHOLD = "cb_parsing_failure_threshold"
    CB_PARSING_RECOVERY_TIMEOUT = "cb_parsing_recovery_timeout"
    CB_KEYPHRASE_FAILURE_THRESHOLD = "cb_keyphrase_failure_threshold"
    CB_KEYPHRASE_RECOVERY_TIMEOUT = "cb_keyphrase_recovery_timeout"
    CB_AUTOPARSE_FAILURE_THRESHOLD = "cb_autoparse_failure_threshold"
    CB_AUTOPARSE_RECOVERY_TIMEOUT = "cb_autoparse_recovery_timeout"
    CB_INTERVIEW_FAILURE_THRESHOLD = "cb_interview_failure_threshold"
    CB_INTERVIEW_RECOVERY_TIMEOUT = "cb_interview_recovery_timeout"
    CB_INTERVIEW_PREP_FAILURE_THRESHOLD = "cb_interview_prep_failure_threshold"
    CB_INTERVIEW_PREP_RECOVERY_TIMEOUT = "cb_interview_prep_recovery_timeout"
    CB_INTERVIEW_QA_FAILURE_THRESHOLD = "cb_interview_qa_failure_threshold"
    CB_INTERVIEW_QA_RECOVERY_TIMEOUT = "cb_interview_qa_recovery_timeout"
    CB_VACANCY_SUMMARY_FAILURE_THRESHOLD = "cb_vacancy_summary_failure_threshold"
    CB_VACANCY_SUMMARY_RECOVERY_TIMEOUT = "cb_vacancy_summary_recovery_timeout"
    CB_ACHIEVEMENTS_FAILURE_THRESHOLD = "cb_achievements_failure_threshold"
    CB_ACHIEVEMENTS_RECOVERY_TIMEOUT = "cb_achievements_recovery_timeout"
    CB_WORK_EXPERIENCE_AI_FAILURE_THRESHOLD = "cb_work_experience_ai_failure_threshold"
    CB_WORK_EXPERIENCE_AI_RECOVERY_TIMEOUT = "cb_work_experience_ai_recovery_timeout"
    CB_RECOMMENDATION_LETTER_FAILURE_THRESHOLD = "cb_recommendation_letter_failure_threshold"
    CB_RECOMMENDATION_LETTER_RECOVERY_TIMEOUT = "cb_recommendation_letter_recovery_timeout"


# ---------------------------------------------------------------------------
# Scraper / HH.ru
# ---------------------------------------------------------------------------

HH_DEFAULT_PAGE_DELAY = (1.0, 2.0)
HH_DEFAULT_VACANCY_DELAY = (1.0, 2.5)
HH_DEFAULT_TIMEOUT = 15
HH_DEFAULT_RETRIES = 3
HH_RATE_LIMIT_REQUESTS = 5
HH_RATE_LIMIT_WINDOW_SECONDS = 1


# ---------------------------------------------------------------------------
# AI / OpenAI
# ---------------------------------------------------------------------------

AI_MAX_DESCRIPTION_LENGTH = 8000
AI_DEFAULT_TIMEOUT = 180
AI_STREAM_TIMEOUT_CONNECT = 10.0
AI_STREAM_TIMEOUT_READ = 30.0
