import asyncio
import logging
import sys

import structlog

from src.config import settings

_CONFIGURED = False


def _build_file_handler(log_dir) -> logging.FileHandler | None:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "hh_bot.log",
            encoding="utf-8",
            mode="a",
        )
    except OSError as exc:
        print(
            f"logging: file logging disabled for {log_dir!s}: {exc}",
            file=sys.stderr,
        )
        return None

    file_handler.setLevel(logging.DEBUG)
    return file_handler


class TelegramLogHandler(logging.Handler):
    """Sends ERROR+ log records to a Telegram chat.

    Reads chat_id from ``settings.log_telegram_chat_id`` on every emit so that
    values changed at runtime via the admin panel take effect immediately.
    """

    def __init__(self, bot_token: str) -> None:
        super().__init__(level=logging.ERROR)
        self._bot_token = bot_token

    def emit(self, record: logging.LogRecord) -> None:
        chat_id = settings.log_telegram_chat_id
        if not chat_id:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        text = self.format(record)
        loop.create_task(self._send(chat_id, text[:4000]))

    async def _send(self, chat_id: str, text: str) -> None:
        import httpx

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": f"🔴 LOG\n\n{text}", "parse_mode": ""}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json=payload)
        except Exception:
            pass


def setup_logging(*, force: bool = False) -> None:
    """Configure structlog + root handlers.

    *force*:
        Clear root handlers and re-apply. Use in Celery worker children after
        fork and when something has replaced ``sys.stderr`` (e.g. Celery's
        stdio redirect): ``StreamHandler(sys.__stderr__)`` still writes the OS
        stderr stream, unlike Rich's handler which follows ``sys.stderr``.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    if force:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    _CONFIGURED = True

    log_dir = settings.log_dir
    root_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared chain for non-structlog records (``foreign_pre_chain``) and as the
    # prefix of the structlog pipeline before ``wrap_for_formatter``.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(root_level)

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=True),
        foreign_pre_chain=shared_processors,
    )
    # Real stderr FD — survives ``sys.stderr = Celery LoggingProxy`` and shows
    # in ``docker logs``; RichHandler followed mutated ``sys.stderr`` and FileHandler
    # still worked from its own file descriptor.
    console_handler = logging.StreamHandler(sys.__stderr__)
    console_handler.setLevel(root_level)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=False),
        foreign_pre_chain=shared_processors,
    )
    file_handler = _build_file_handler(log_dir)
    if file_handler is not None:
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    tg_handler = TelegramLogHandler(settings.bot_token)
    tg_handler.setFormatter(file_formatter)
    root_logger.addHandler(tg_handler)

    for noisy in ("httpx", "httpcore", "asyncio", "aiohttp", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    setup_logging()
    return structlog.get_logger(name)
