"""Typed data transfer objects used across module boundaries.

All raw dicts flowing between services, tasks, and repositories must be
replaced with one of these typed structures.
"""

from src.schemas.ai import ImprovementItem, QAPair
from src.schemas.progress import ProgressBarState, ProgressTaskState
from src.schemas.task import TaskNotification
from src.schemas.vacancy import PipelineResult, VacancyData

__all__ = [
    "PipelineResult",
    "VacancyData",
    "QAPair",
    "ImprovementItem",
    "ProgressBarState",
    "ProgressTaskState",
    "TaskNotification",
]
