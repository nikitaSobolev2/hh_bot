# HH Bot — Full Overhaul: Refactoring Results

> Generated: March 2026  
> Scope: Phases 1–7 of the Full Overhaul Plan

---

## Overview

This document summarises the changes made during the comprehensive refactoring of HH Bot.
The goal was to make the system production-ready for **100 concurrent users** while keeping
the codebase clean, testable, and maintainable.

---

## Phase 1 — Worker Stability & Scalability

### `HHBotTask` base class (`src/worker/base_task.py`)

All 14 Celery tasks now inherit from `HHBotTask` instead of the plain `Task` base.
The base class centralises previously duplicated boilerplate:

| Capability | Method |
|---|---|
| Feature-flag check | `check_enabled(key, session_factory)` |
| Circuit-breaker setup | `load_circuit_breaker(name, threshold_key, timeout_key, sf)` |
| Bot creation | `create_bot()` |
| User notification (edit/send) | `notify_user(bot, chat_id, message_id, text, ...)` |
| Idempotency check | `is_already_completed(key, sf)` |
| Idempotency mark | `mark_completed(key, task_type, ref_id, sf)` |
| Soft-timeout handler | `handle_soft_timeout(bot, chat_id, message_id, locale, ...)` |
| Per-user deduplication lock | `acquire_user_task_lock(user_id, task_type, ttl)` |
| Lock release | `release_user_task_lock(user_id, task_type)` |

### Rate limiter (`src/worker/throttle.py`)

A Redis-backed sliding-window `RateLimiter` was introduced:

```python
class RateLimiter:
    async def acquire(self) -> None: ...  # blocks until a slot is available
```

Both the HH.ru scraper (`HHScraper`) and the OpenAI client (`AIClient`) accept an
optional `rate_limiter` argument so external call rates can be governed centrally.

### Task time limits

Every task now declares explicit Celery `soft_time_limit` and `time_limit` values,
paired with a `SoftTimeLimitExceeded` handler that:
1. Notifies the user in Telegram.
2. Optionally marks the idempotency key as failed.
3. Exhausts retries to prevent repeated timeouts.

### Circuit breaker coverage

New `AppSettingKey` constants were added for tasks that previously lacked
DB-configurable CB thresholds:

- `CB_INTERVIEW_ANALYSIS_*`, `CB_IMPROVEMENT_FLOW_*`
- `CB_PREP_GUIDE_*`, `CB_PREP_DEEP_SUMMARY_*`, `CB_PREP_TEST_*`

---

## Phase 2 — Prompt Quality & Security

### System / user prompt separation

Every AI call in the codebase now uses two messages:

| Role | Content |
|---|---|
| `system` | Persona, rules, format spec, anti-injection instruction |
| `user` | Sanitised, XML-wrapped user data |

New `build_*_system_prompt()` functions were added for all nine feature prompts
that previously bundled both concerns into a single user message.

### Prompt injection protection

All user-supplied free-form text is wrapped with `_wrap_user_input()`:

```python
def _wrap_user_input(label: str, value: str) -> str:
    return f"<{label}>\n{value}\n</{label}>"
```

Every system prompt includes `_ANTI_INJECTION`, an explicit instruction telling
the model to disregard instructions embedded in user data.

### Achievement hallucination fix

`build_achievement_generation_system_prompt()` no longer contains a fallback that
said *"invent metrics if none provided"*. The new rule is:

> Use job title and tech stack only — generate realistic bullets based on actual
> technologies. No invented metrics. No vague adverbs.

### Context truncation limits increased

| Prompt | Old limit | New limit |
|---|---|---|
| Preparation guide — vacancy description | 2 000 chars | 4 000 chars |
| Deep learning summary — vacancy context | 1 500 chars | 3 000 chars |

---

## Phase 3 — Shared UI Infrastructure

### `src/bot/ui/keyboards.py` — `step_keyboard`

```python
def step_keyboard(
    step: int,
    total: int,
    back_callback: str,
    cancel_callback: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup: ...
```

Returns a consistent Back / Cancel row for every FSM step.
Back is hidden on the first step.

### `src/bot/ui/templates.py` — `error_template` & `progress_template`

```python
def error_template(key: str, i18n: I18nContext) -> str: ...

def progress_template(title: str, percent: int) -> str:
    # renders:  ⏳ **Title**
    #           [████████░░] 80%
```

### New i18n keys (both `ru` and `en` locales)

| Key | Purpose |
|---|---|
| `task-soft-timeout` | Soft time limit user message |
| `task-progress-started` | Task queued confirmation |
| `btn-edit-field` | Inline "edit field" button |
| `btn-review` | Inline "review answers" button |
| `form-step-counter` | "Step N of M" label |
| `form-review-title` | Review screen title |
| `prep-guide-failed` | Prep guide error |
| `prep-deep-failed` | Deep summary error |
| `prep-test-failed` | Test generation error |
| `res-rec-letter-failed` | Recommendation letter error |

---

## Phase 4 — Form UX: Back, Review, Progress Bars & Data Deduplication

### Achievement pre-population from work experience

When a user opens the achievement generator the form is now pre-populated:

```python
# before
ach_achievements=[None] * len(experiences),
ach_responsibilities=[None] * len(experiences),

# after
ach_achievements=[exp.achievements or None for exp in experiences],
ach_responsibilities=[exp.duties or None for exp in experiences],
```

If a user previously generated AI achievements/duties for a job they will see those
values when revisiting the achievement form, eliminating duplication.

The input prompt also shows a *"Current value"* hint when a field is pre-populated,
so the user knows they can skip or overwrite it.

---

## Phase 5 — Consistent Module Message Templates

`error_template` and `progress_template` from `src/bot/ui/templates.py` are available
to all 13 modules. The `step_keyboard` factory is the canonical way to build
Back / Cancel navigation for any multi-step FSM form.

---

## Phase 6 — Documentation

- **`docs/REFACTORING_RESULTS.md`** (this file) — summarises all changes.
- **`docs/BEST_PRACTICES.md`** — updated with new sections on prompt engineering,
  circuit breakers, rate limiting, and the `HHBotTask` pattern.

---

## Phase 7 — Tests & Linting

### Test suite

| Metric | Value |
|---|---|
| Total tests | 678 |
| Passing | 678 |
| Failing | 0 |

Updated test files:

| File | Reason |
|---|---|
| `tests/unit/test_achievement_prompts.py` | Format markers moved to system prompt |
| `tests/unit/test_interview_prep_prompts.py` | Format markers moved to system prompt |
| `tests/unit/test_interview_tasks.py` | Rewritten for `HHBotTask` interface (no `_load_circuit_breaker_config`) |

### Linting

`ruff check src/ tests/` — **0 errors**.  
`ruff format src/ tests/` — all files formatted.

---

## Architecture Summary

```
src/
├── bot/
│   ├── modules/          # 13 feature modules (handlers, keyboards, services)
│   └── ui/
│       ├── keyboards.py  # step_keyboard, cancel_keyboard, confirm_keyboard
│       └── templates.py  # MessageTemplate, error_template, progress_template
├── core/
│   └── constants.py      # AppSettingKey (all CB / feature-flag keys)
├── services/
│   ├── ai/
│   │   ├── client.py     # AIClient with rate_limiter support
│   │   └── prompts.py    # system+user split for all 9 feature prompts
│   └── parser/
│       └── scraper.py    # HHScraper with rate_limiter support
└── worker/
    ├── base_task.py      # HHBotTask base class
    ├── throttle.py       # RateLimiter (Redis sliding window)
    ├── circuit_breaker.py
    └── tasks/            # 14 tasks, all inheriting HHBotTask
```

---

## Key Decisions

| Decision | Rationale |
|---|---|
| Centralise boilerplate in `HHBotTask` | Eliminated ~200 lines of duplicated setup across tasks |
| Redis sliding-window rate limiter | Prevents throttling by HH.ru and OpenAI under concurrent load |
| XML wrapping for user inputs | Robust prompt injection defence without complex sanitisation |
| System prompt per feature | Separates AI persona/rules from user data for better model compliance |
| Pre-populate achievement form | Removes user confusion when data they already generated is not visible |
| `contextlib.suppress` for soft-timeout notification | Notification failure must not mask the original SoftTimeLimitExceeded |
