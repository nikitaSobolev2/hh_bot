"""Shared utilities for Celery worker tasks."""

import asyncio
from collections.abc import Coroutine
from typing import Any


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a synchronous Celery task context."""
    return asyncio.run(coro)
