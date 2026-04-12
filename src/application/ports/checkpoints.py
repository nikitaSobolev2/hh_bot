"""Checkpoint persistence contracts."""

from __future__ import annotations

from typing import Any, Protocol


class CheckpointStore(Protocol):
    """Minimal persistence contract for resumable task checkpoints."""

    async def save_json(self, key: str, payload: dict[str, Any]) -> None:
        """Persist JSON-serializable checkpoint payload under a fully-qualified Redis key."""

    async def load_json(self, key: str) -> dict[str, Any] | None:
        """Load checkpoint payload from a fully-qualified Redis key."""

    async def delete(self, key: str) -> None:
        """Delete checkpoint payload by fully-qualified Redis key."""
