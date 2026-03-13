"""Typed schemas for AI service inputs and outputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QAPair:
    """A single interview question/answer pair."""

    question: str
    answer: str

    def to_dict(self) -> dict[str, str]:
        return {"question": self.question, "answer": self.answer}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> QAPair:
        return cls(question=data["question"], answer=data["answer"])


@dataclass(frozen=True)
class ImprovementItem:
    """A single AI-generated improvement recommendation."""

    title: str
    summary: str
