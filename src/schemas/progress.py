"""Typed schemas for progress service state stored in Redis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProgressBarState:
    """State for a single progress bar within a task."""

    label: str
    current: int = 0
    total: int = 0
    done: bool = False

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "current": self.current,
            "total": self.total,
            "done": self.done,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProgressBarState:
        return cls(
            label=data["label"],
            current=data.get("current", 0),
            total=data.get("total", 0),
            done=data.get("done", False),
        )


@dataclass
class ProgressTaskState:
    """State for a named progress task (which may have multiple bars)."""

    title: str
    bars: list[ProgressBarState] = field(default_factory=list)
    done: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "bars": [b.to_dict() for b in self.bars],
            "done": self.done,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProgressTaskState:
        return cls(
            title=data["title"],
            bars=[ProgressBarState.from_dict(b) for b in data.get("bars", [])],
            done=data.get("done", False),
        )
