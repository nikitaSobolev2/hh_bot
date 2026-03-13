# HH Bot — Best Practices Reference

This document is the authoritative guide for all development in this codebase.
Every pull request, feature, bug fix, and refactoring must conform to these standards.

---

## Table of Contents

1. [Clean Code (Uncle Bob)](#1-clean-code-uncle-bob)
2. [Clean Architecture Layers](#2-clean-architecture-layers)
3. [Python 3.12+ Conventions](#3-python-312-conventions)
4. [aiogram 3 Best Practices](#4-aiogram-3-best-practices)
5. [Celery Best Practices](#5-celery-best-practices)
6. [Redis Best Practices](#6-redis-best-practices)
7. [SQLAlchemy Async Best Practices](#7-sqlalchemy-async-best-practices)
8. [pytest Best Practices](#8-pytest-best-practices)
9. [Broker Stability Patterns](#9-broker-stability-patterns)
10. [Checklist Before Merging](#10-checklist-before-merging)

---

## 1. Clean Code (Uncle Bob)

### Naming

- Names must answer: *why it exists*, *what it does*, *how it is used*.
- No abbreviations: use `parsing_company`, not `pc`; `vacancy_title`, not `vt`.
- No single-letter variables except `i`, `j` in trivial loops and `_` for ignored values.
- Class names are nouns or noun phrases: `VacancyFeedSession`, `CircuitBreaker`.
- Method names are verbs or verb phrases: `calculate_compatibility`, `record_failure`.
- One word per concept — pick one and use it everywhere:
  - Use `fetch_` for DB lookups, `build_` for constructors, `create_` for factories.
  - Do **not** mix `get_`, `fetch_`, `retrieve_`, `load_` for the same operation type.

### Functions

- **Single responsibility**: one function does one thing.
- **Short**: aim for under 20 lines; extract named helpers if longer.
- **0–2 arguments** is ideal; 3+ signals a parameter object.
- **No side effects** in query functions: `build_compatibility_prompt` must not call OpenAI.
- **Command-Query Separation**: a function either mutates state (command) or returns a value (query) — never both.
- **No flag arguments** (`do_foo(enable=True)`): split into two functions instead.

```python
# Good — single responsibility, descriptive name
def _format_work_experience_line(experience: WorkExperienceEntry) -> str:
    parts = [experience.company_name]
    if experience.title:
        parts.append(f"— {experience.title}")
    if experience.period:
        parts.append(f"({experience.period})")
    return " ".join(parts)

# Bad — mixed concerns, abbreviations, unclear name
def fmt(exp, with_stack=False):
    s = exp.cn
    if exp.t:
        s += f" {exp.t}"
    if with_stack:
        s += f" [{exp.stack}]"
    return s
```

### Comments

- Do **not** comment what the code already says.
- Acceptable: algorithm intent, trade-off explanations, `TODO/FIXME` with ticket references.
- Never use comments to disable code — delete it instead.

### Error Handling

- Raise exceptions; never return `None` to signal failure.
- Use `Optional[T]` or empty collections only when *absence is a valid, expected outcome*.
- Keep `try` blocks narrow — only the one line that can raise belongs inside.
- Handle exceptions at the correct abstraction level (a repository raises `RepositoryError`, not `sqlalchemy.exc.IntegrityError` visible to the caller).

---

## 2. Clean Architecture Layers

```
Telegram Update
     │
     ▼
┌────────────────┐
│  Bot Handlers  │  aiogram routers, FSM, keyboards, callbacks
│  (src/bot/)    │  — Thin orchestrators: validate input, delegate, render output
└───────┬────────┘
        │ calls
        ▼
┌────────────────┐
│   Services     │  Business logic, AI calls, scraping, formatting
│(src/services/) │  — No knowledge of Telegram types or HTTP responses
└───────┬────────┘
        │ calls
        ▼
┌────────────────┐
│  Repositories  │  All DB access — one class per model
│(src/repos/)    │  — No business logic, only CRUD and query building
└───────┬────────┘
        │ reads/writes
        ▼
┌────────────────┐
│    Models      │  SQLAlchemy ORM, pure data definitions
│ (src/models/)  │
└────────────────┘
```

**Rules:**
- Handlers never import from `src.models` directly.
- Handlers never write raw SQL or call `session.execute`.
- Services never import from `src.bot`.
- Repositories never contain business logic.
- Workers (Celery tasks) call services and repositories, never bot handlers.

---

## 3. Python 3.12+ Conventions

### Type Annotations

- Annotate **all** function signatures — parameters and return types.
- Use `from __future__ import annotations` at the top of files with forward references.
- Use `X | Y` union syntax (not `Union[X, Y]`).
- Use `type` keyword for type aliases:

```python
type VacancyId = int
type KeywordList = list[str]
```

- Use `TypedDict` for structured dicts that cross module boundaries (prefer `@dataclass` or Pydantic for richer validation).
- Use `Protocol` for structural interfaces (dependency inversion without ABC).

### Dataclasses and Pydantic

- Use `@dataclass(frozen=True)` for immutable value objects.
- Use Pydantic `BaseModel` for external-facing schemas (API responses, config).
- Never pass raw `dict` across module boundaries — use typed models.

```python
# Good
@dataclass(frozen=True)
class VacancyData:
    hh_vacancy_id: str
    url: str
    title: str
    raw_skills: list[str]
    description: str = ""
    ai_keywords: list[str] = field(default_factory=list)

# Bad
def process(vac: dict) -> dict:
    return {"id": vac["id"], ...}
```

### Async

- Use `async/await` throughout. Never block the event loop.
- Use `asyncio.to_thread` for unavoidably sync operations (e.g., `bcrypt`).
- Never call `asyncio.run()` inside an async function.

---

## 4. aiogram 3 Best Practices

### Router Architecture

- **One `Router` per feature module**, exposed from `__init__.py`.
- Register routers in `src/bot/create.py` in a fixed, documented order.
- Never register handlers directly on the global `Dispatcher`.

```python
# src/bot/modules/parsing/__init__.py
from src.bot.modules.parsing.handlers.setup import router as setup_router
from src.bot.modules.parsing.handlers.results import router as results_router

router = Router(name="parsing")
router.include_router(setup_router)
router.include_router(results_router)
```

### FSM States

- Define states in `states.py` as `StatesGroup` subclasses.
- Always call `await state.clear()` in every terminal handler (success, cancel, error).
- Store only serializable primitives in FSM state data (`str`, `int`, `bool`, `list[int]`).

```python
# states.py
class ParsingStates(StatesGroup):
    waiting_url = State()
    waiting_count = State()
    waiting_keywords = State()
```

### Callback Data

- Use typed `CallbackData` subclasses with a unique `prefix` for every action set.
- Never construct or parse callback strings manually.
- Use `Enum` for `action` fields to prevent typos.
- Do **not** overload a single field for multiple semantic meanings.

```python
from enum import StrEnum

class ParsingAction(StrEnum):
    view = "view"
    export = "export"
    delete = "delete"

class ParsingCallback(CallbackData, prefix="prs"):
    action: ParsingAction
    company_id: int
```

### Handlers

- First line of every `callback_query` handler: `await callback.answer()`.
- For operations > 2 seconds: answer immediately, delegate to Celery.
- Handlers return in milliseconds — zero blocking I/O.
- Use `CallbackAnswerMiddleware` to auto-answer callbacks globally.

```python
@router.callback_query(ParsingCallback.filter(F.action == ParsingAction.view))
async def view_parsing_result(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    session: AsyncSession,
    locale: str,
) -> None:
    await callback.answer()
    # ... fast DB read only
```

### Keyboards

- Build keyboards in `keyboards.py` using `InlineKeyboardBuilder`.
- Keyboard builders accept `locale: str` for i18n text.
- Use `builder.adjust(2)` for consistent row widths.
- Standard layout rules:
  - Primary action: top-left
  - Max 2 buttons per action row
  - Pagination row: second to last
  - Back/Cancel button: last row, full width

```python
def build_parsing_detail_keyboard(company_id: int, locale: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text("btn-export", locale),
        callback_data=ParsingCallback(action=ParsingAction.export, company_id=company_id),
    )
    builder.button(
        text=get_text("btn-delete", locale),
        callback_data=ParsingCallback(action=ParsingAction.delete, company_id=company_id),
    )
    builder.button(
        text=get_text("btn-back", locale),
        callback_data=MenuCallback(action="my_parsings"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()
```

### Middleware

- Middleware order in `create_dispatcher()`:
  1. `ThrottleMiddleware` — reject overloaded users early
  2. `AuthMiddleware` — load user, check ban, inject `user` and `session`
  3. `LocaleMiddleware` — inject `locale`

- Middleware must be fast — no heavy I/O.
- Use `data["key"]` to pass objects downstream to handlers.

### i18n

- All user-visible text lives in `src/locales/ru/LC_MESSAGES/messages.ftl` and its `en` counterpart.
- Never hardcode Russian or English strings in handler or keyboard files.
- Use `get_text(key, locale, **kwargs)` from `src/core/i18n.py` everywhere.
- FTL key naming: `<module>-<element>-<description>` (e.g., `parsing-btn-export`, `ach-generation-completed`).

---

## 5. Celery Best Practices

### Task Definition

```python
@celery_app.task(
    bind=True,
    name="achievements.generate",          # Always explicit name
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,                   # Raise SoftTimeLimitExceeded for cleanup
    time_limit=300,                        # Hard kill after this
    acks_late=True,                        # Acknowledge only after execution
    reject_on_worker_lost=True,            # Requeue on worker crash
)
def generate_achievements_task(self, generation_id: int, ...) -> dict:
    return run_async(lambda sf: _generate_async(sf, self, generation_id, ...))
```

### Ack / Nack

- **Global defaults** in `src/worker/app.py`:
  ```python
  task_acks_late = True
  task_reject_on_worker_lost = True
  task_acks_on_failure_or_timeout = False
  worker_prefetch_multiplier = 1
  ```
- Per-task `acks_late=True` is **redundant** when global is set — do not repeat it unless explicitly overriding.
- For non-idempotent tasks that must not be retried: set `acks_late=False` explicitly.

### Retry Pattern

```python
@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def my_task(self, item_id: int) -> dict:
    return run_async(lambda sf: _my_task_async(sf, self, item_id))

async def _my_task_async(session_factory, task, item_id: int) -> dict:
    try:
        # ... do work ...
    except TransientError as exc:
        raise task.retry(exc=exc, countdown=30)
    except PermanentError as exc:
        # Do NOT retry — log and mark failed
        logger.error("Permanent failure", error=str(exc))
        raise
```

### Idempotency

Every task that can be retried **must** be idempotent:

1. Generate an idempotency key before starting.
2. Check if the key exists in `celery_tasks` table with `status="completed"`.
3. If yes: return early with `{"status": "already_completed"}`.
4. On success: persist the key with `status="completed"`.

```python
idempotency_key = f"generate_achievements:{generation_id}"
async with session_factory() as session:
    existing = await CeleryTaskRepository(session).get_by_idempotency_key(idempotency_key)
    if existing and existing.status == "completed":
        return {"status": "already_completed"}
```

### Task Enable Flags

Every task must check its feature flag before processing:

```python
async with session_factory() as session:
    enabled = await AppSettingRepository(session).get_value("task_achievements_enabled", default=True)
if not enabled:
    return {"status": "disabled"}
```

Feature flags in `app_settings`:
- `task_parsing_enabled`
- `task_autoparse_enabled`
- `task_keyphrase_enabled`
- `task_interview_analysis_enabled`
- `task_improvement_flow_enabled`
- `task_interview_prep_enabled`
- `task_interview_qa_enabled`
- `task_vacancy_summary_enabled`
- `task_achievements_enabled`
- `task_work_experience_ai_enabled`

### SoftTimeLimitExceeded

Always handle `SoftTimeLimitExceeded` for cleanup:

```python
from billiard.exceptions import SoftTimeLimitExceeded

try:
    result = await ai_client.generate_text(prompt)
except SoftTimeLimitExceeded:
    await _mark_failed(session_factory, generation_id)
    await _notify_user_timeout(bot_token, chat_id, message_id, locale)
    raise
```

### Bot Creation in Tasks

Use the shared factory — never inline:

```python
from src.services.telegram.bot_factory import create_task_bot

bot = create_task_bot()
try:
    await _do_work(bot, ...)
finally:
    await bot.session.close()
```

---

## 6. Redis Best Practices

### Key Naming Convention

Format: `<namespace>:<entity_type>:<id>`

| Namespace | Owner | Example |
|-----------|-------|---------|
| `cb:` | `CircuitBreaker` | `cb:parsing:state` |
| `progress:` | `ProgressService` | `progress:chat:123456` |
| `checkpoint:` | `TaskCheckpointService` | `checkpoint:autoparse_run:7` |
| `lock:` | Celery tasks | `lock:autoparse:42` |
| `throttle:` | `RateLimiter` | `throttle:hh:requests` |

- Always use `SNAKE_CASE` within segments.
- Never mix namespaces between services.

### TTL is Mandatory

Every Redis key **must** have a TTL. No persistent keys allowed.

```python
# Good
await redis.set("progress:chat:123", data, ex=3600)
await redis.set("lock:autoparse:42", "1", nx=True, ex=300)

# Bad — no TTL
await redis.set("progress:chat:123", data)
```

### Pipelines for Multi-Step Operations

Use `pipeline()` for atomic multi-step read-modify-write:

```python
async with redis.pipeline(transaction=True) as pipe:
    await pipe.set(key_state, STATE_OPEN, ex=3600)
    await pipe.set(key_last_failure, str(time.time()), ex=3600)
    await pipe.execute()
```

### Distributed Locks

Use `SET key NX EX ttl` for mutual exclusion:

```python
acquired = await redis.set(lock_key, "1", nx=True, ex=300)
if not acquired:
    return {"status": "already_running"}
try:
    # ... do work ...
finally:
    await redis.delete(lock_key)
```

### Connection Pooling

- Reuse a single `redis.asyncio.ConnectionPool` per process.
- Do not create a new `Redis` connection per request.
- Use `redis.asyncio.from_url(url, decode_responses=True)` for the async client.

---

## 7. SQLAlchemy Async Best Practices

### Session Lifecycle

- One session per request or task operation — never reuse across independent operations.
- Use `async with session_factory() as session:` everywhere.
- Session auto-commits on context exit; call `await session.commit()` explicitly when needed.

### Repository Pattern

- All DB access goes through `src/repositories/`. Zero raw SQL in handlers or tasks.
- All repositories extend `BaseRepository[T]`.
- Method naming: `get_by_id`, `get_by_user`, `create`, `update`, `delete_by_id`, `list_by_user`.

```python
class AchievementGenerationRepository(BaseRepository[AchievementGeneration]):
    async def get_by_user_paginated(
        self, user_id: int, *, page: int, page_size: int
    ) -> tuple[list[AchievementGeneration], int]:
        offset = (page - 1) * page_size
        count_stmt = select(func.count()).select_from(AchievementGeneration).where(
            AchievementGeneration.user_id == user_id
        )
        total = await self._session.scalar(count_stmt) or 0
        stmt = (
            select(AchievementGeneration)
            .where(AchievementGeneration.user_id == user_id)
            .order_by(AchievementGeneration.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total
```

### Eager Loading

Always specify `selectinload()` or `joinedload()` for relationships you'll access:

```python
stmt = (
    select(AchievementGeneration)
    .where(AchievementGeneration.id == generation_id)
    .options(selectinload(AchievementGeneration.items).selectinload(AchievementItem.work_experience))
)
```

Never rely on lazy loading — it raises `MissingGreenlet` in async context.

### Count Queries

Use `func.count()` — never `len(result.scalars().all())`:

```python
# Good
count = await session.scalar(select(func.count()).select_from(MyModel).where(...))

# Bad — loads all rows to count them
count = len((await session.execute(select(MyModel).where(...))).scalars().all())
```

### Consistency

- Use `scalar_one_or_none()` for single-row lookups (not `scalars().first()`).
- Use `scalar()` for aggregate queries.
- Use `scalars().all()` for multi-row reads.

---

## 8. pytest Best Practices

### F.I.R.S.T.

- **Fast**: mock all I/O. No real DB, Redis, HTTP, or AI calls.
- **Independent**: no shared mutable state between tests.
- **Repeatable**: same result every run.
- **Self-validating**: explicit assertions, no "check the logs" tests.
- **Timely**: written with or before the feature.

### Test Naming

```python
# Pattern: test_<subject>_<scenario>_<expected_outcome>

def test_circuit_breaker_records_failure_increments_count(): ...
def test_circuit_breaker_at_threshold_transitions_to_open(): ...
def test_achievements_task_circuit_open_returns_early(): ...
def test_achievements_task_success_marks_generation_completed(): ...
```

### One Assertion Per Test

```python
# Good
def test_parse_achievement_blocks_returns_company_name_as_key():
    result = _parse_achievement_blocks("[AchStart]:Acme\nDid great work\n[AchEnd]:Acme")
    assert "Acme" in result

def test_parse_achievement_blocks_returns_content_as_value():
    result = _parse_achievement_blocks("[AchStart]:Acme\nDid great work\n[AchEnd]:Acme")
    assert result["Acme"] == "Did great work"

# Bad — multiple assertions in one test
def test_parse_achievement_blocks():
    result = _parse_achievement_blocks(...)
    assert "Acme" in result
    assert result["Acme"] == "Did great work"
    assert len(result) == 1
```

### Fixtures

```python
@pytest.fixture
def make_session_factory():
    """Return a factory that yields a mock async session."""
    def _factory(session: AsyncMock) -> AsyncMock:
        factory = AsyncMock()
        factory.return_value.__aenter__.return_value = session
        factory.return_value.__aexit__.return_value = None
        return factory
    return _factory

@pytest.fixture
def mock_ai_client(mocker) -> MagicMock:
    client = mocker.patch("src.services.ai.client.AIClient")
    return client.return_value
```

### Mocking Rules

| What to mock | How |
|---|---|
| `httpx` HTTP calls | `respx` fixtures |
| `AsyncOpenAI` | `AsyncMock` on `AIClient` methods |
| Redis calls | `AsyncMock` on `redis.asyncio.Redis` |
| DB sessions | `AsyncMock` session + `make_session_factory` fixture |
| Filesystem | `unittest.mock.patch("builtins.open", ...)` |
| Bot API | `AsyncMock` on `Bot` methods |

### Parametrize for Multiple Inputs

```python
@pytest.mark.parametrize("expression,title,expected", [
    ("python|django", "Python developer", True),
    ("python|django", "Java developer", False),
    ("python,django", "Python Django developer", True),
    ("python,django", "Python developer", False),
    ("", "Any title", True),
])
def test_matches_keyword_expression(expression: str, title: str, expected: bool) -> None:
    assert matches_keyword_expression(title, expression) is expected
```

---

## 9. Broker Stability Patterns

### Circuit Breaker

Every task that calls OpenAI or HH.ru **must** use `CircuitBreaker`:

```python
cb = CircuitBreaker("achievements")
cb.update_config(
    failure_threshold=int(await settings_repo.get_value("cb_achievements_failure_threshold", 5)),
    recovery_timeout=int(await settings_repo.get_value("cb_achievements_recovery_timeout", 60)),
)
if not cb.is_call_allowed():
    return {"status": "circuit_open"}

try:
    result = await ai_client.generate_text(prompt)
    cb.record_success()
except Exception as exc:
    cb.record_failure()
    raise
```

Circuit breaker states:
- `CLOSED`: normal operation
- `OPEN`: failing, reject all calls
- `HALF_OPEN`: recovery probe — allow one call; close on success, reopen on failure

### Rate Limiting (Throttling)

Use `RateLimiter` from `src/worker/throttle.py` before every external API call:

```python
from src.worker.throttle import RateLimiter

limiter = RateLimiter(redis_client, namespace="hh", max_requests=5, window_seconds=1)
await limiter.acquire()  # blocks until token available
response = await scraper.fetch(url)
```

OpenAI limits:
- Respect `429 Too Many Requests` — back off exponentially.
- Use `httpx.Timeout(connect=10, read=300)` for long generations.

### Idempotency Key Lifecycle

```
Task starts
    │
    ▼
Check idempotency_key in celery_tasks table
    │
    ├── exists + status="completed" → return {"status": "already_completed"}
    │
    └── not exists or status!="completed"
            │
            ▼
        Do work
            │
            ├── success → persist key with status="completed"
            │
            └── failure → persist key with status="failed", raise
```

### Distributed Locks

For tasks where exactly-once execution within a time window matters:

```python
lock_key = f"lock:autoparse:{company_id}"
acquired = await redis.set(lock_key, "1", nx=True, ex=300)
if not acquired:
    return {"status": "already_running"}
try:
    # ... do work ...
finally:
    await redis.delete(lock_key)
```

### Notification Pattern (Edit-or-Send Fallback)

When a task completes and needs to update the user's message:

```python
from src.services.telegram.messenger import TelegramMessenger

messenger = TelegramMessenger(bot)
await messenger.edit_or_send(
    chat_id=chat_id,
    message_id=message_id,
    text=get_text("ach-generation-completed", locale),
    reply_markup=keyboard,
)
```

`edit_or_send` tries `edit_message_text` first; falls back to `send_message` on `TelegramBadRequest`.

---

## 10. Checklist Before Merging

- [ ] `ruff check src/ tests/` passes with zero errors
- [ ] `ruff format src/ tests/` applied
- [ ] `pytest` passes with zero failures
- [ ] No `print()` statements added
- [ ] All new public functions have type annotations
- [ ] No raw `os.environ` access (use `settings`)
- [ ] No SQL outside a repository class
- [ ] No raw `dict` crossing module boundaries — use typed dataclasses
- [ ] Every Redis key has a TTL
- [ ] Every task calling OpenAI or HH.ru uses `CircuitBreaker`
- [ ] Every task has an idempotency check
- [ ] Every task has a `task_*_enabled` flag check
- [ ] Every task has explicit `soft_time_limit` and `time_limit`
- [ ] New user-visible strings are in Fluent `.ftl` files (no hardcoded text)
- [ ] New repositories extend `BaseRepository`
- [ ] New features have matching unit tests in `tests/unit/`
