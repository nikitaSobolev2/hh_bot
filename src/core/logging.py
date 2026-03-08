import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
from rich.console import Console
from rich.logging import RichHandler

from src.config import settings

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_CONFIGURED = False


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


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    console_handler = RichHandler(
        console=Console(stderr=True),
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_time=True,
        show_path=False,
        markup=True,
        level=logging.INFO,
    )
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        _LOG_DIR / "hh_bot.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(file_handler)

    tg_handler = TelegramLogHandler(settings.bot_token)
    tg_handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s\n%(message)s"))
    root_logger.addHandler(tg_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    for noisy in ("httpx", "httpcore", "asyncio", "aiohttp", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    setup_logging()
    return structlog.get_logger(name)
