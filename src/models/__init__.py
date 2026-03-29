from src.models.achievement import AchievementGeneration, AchievementGenerationItem
from src.models.app_settings import AppSetting
from src.models.autoparse import AutoparseCompany, AutoparsedVacancy
from src.models.balance import BalanceTransaction
from src.models.ban import UserBan
from src.models.blacklist import VacancyBlacklist
from src.models.cover_letter_vacancy import CoverLetterVacancy
from src.models.hh import HHArea, HHEmployer
from src.models.hh_application_attempt import HhApplicationAttempt
from src.models.hh_linked_account import HhLinkedAccount
from src.models.interview import (
    Interview,
    InterviewEmployerQuestion,
    InterviewImprovement,
    InterviewNote,
    InterviewPreparationStep,
    InterviewPreparationTest,
    InterviewQuestion,
)
from src.models.interview_qa import StandardQuestion
from src.models.parsing import AggregatedResult, ParsedVacancy, ParsingCompany
from src.models.recommendation_letter import RecommendationLetter
from src.models.referral import ReferralEvent
from src.models.resume import Resume
from src.models.role import Role, RolePermission
from src.models.support import SupportAttachment, SupportMessage, SupportTicket
from src.models.task import (
    BaseCeleryTask,
    CompanyCreateKeyPhrasesTask,
    CompanyParseKeywordsFromDescriptionTask,
    CompanyParseTask,
    CoverLetterTask,
    InterviewQATask,
)
from src.models.user import User
from src.models.vacancy_feed import VacancyFeedSession
from src.models.vacancy_summary import VacancySummary
from src.models.work_experience import UserWorkExperience
from src.models.work_experience_ai_draft import UserWorkExperienceAiDraft

__all__ = [
    "Role",
    "RolePermission",
    "User",
    "AutoparseCompany",
    "AutoparsedVacancy",
    "CoverLetterVacancy",
    "UserWorkExperience",
    "UserWorkExperienceAiDraft",
    "VacancyFeedSession",
    "ParsingCompany",
    "ParsedVacancy",
    "AggregatedResult",
    "VacancyBlacklist",
    "BaseCeleryTask",
    "CompanyParseKeywordsFromDescriptionTask",
    "CompanyCreateKeyPhrasesTask",
    "CompanyParseTask",
    "CoverLetterTask",
    "InterviewQATask",
    "AppSetting",
    "BalanceTransaction",
    "ReferralEvent",
    "SupportTicket",
    "SupportMessage",
    "SupportAttachment",
    "UserBan",
    "Interview",
    "InterviewEmployerQuestion",
    "InterviewQuestion",
    "InterviewImprovement",
    "InterviewNote",
    "InterviewPreparationStep",
    "InterviewPreparationTest",
    "AchievementGeneration",
    "AchievementGenerationItem",
    "StandardQuestion",
    "VacancySummary",
    "Resume",
    "RecommendationLetter",
    "HHEmployer",
    "HHArea",
    "HhLinkedAccount",
    "HhApplicationAttempt",
]
