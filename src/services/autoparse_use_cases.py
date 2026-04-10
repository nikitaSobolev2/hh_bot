from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autoparse import AutoparseCompany
from src.models.user import User
from src.repositories.app_settings import AppSettingRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository

if TYPE_CHECKING:
    from src.core.i18n import I18nContext


@dataclass(slots=True)
class AutoparseCompanyDetailView:
    text: str
    vacancies_count: int
    show_run_now: bool
    show_show_now: bool
    show_sync_negotiations: bool
    autorespond_task_enabled: bool


def format_company_detail(
    company: AutoparseCompany,
    vacancies_count: int,
    i18n: I18nContext,
    *,
    autorespond_global: bool = False,
    autorespond_task_enabled: bool | None = None,
) -> str:
    status = (
        i18n.get("autoparse-status-enabled")
        if company.is_enabled
        else i18n.get("autoparse-status-disabled")
    )
    keyword_check_enabled = company.keyword_check_enabled is not False
    keyword_check_status = i18n.get("yes") if keyword_check_enabled else i18n.get("no")
    last_run = company.last_parsed_at.strftime("%Y-%m-%d %H:%M") if company.last_parsed_at else "—"
    url_label = i18n.get("autoparse-detail-url")
    lines = [
        f"<b>{i18n.get('autoparse-detail-title')}</b>",
        "",
        f"<b>{company.vacancy_title}</b>",
        f"{i18n.get('autoparse-detail-status')}: {status}",
        f"{url_label}: <a href='{company.search_url}'>{url_label}</a>",
        f"{i18n.get('autoparse-detail-parse-mode')}: "
        f"{i18n.get('autoparse-parse-mode-web-label' if company.parse_mode == 'web' else 'autoparse-parse-mode-api-label')}",
        f"{i18n.get('autoparse-detail-keywords')}: {company.keyword_filter or '—'}",
        f"{i18n.get('autoparse-detail-keyword-check')}: {keyword_check_status}",
        f"{i18n.get('autoparse-detail-skills')}: {company.skills or '—'}",
        "",
        f"{i18n.get('autoparse-detail-metrics')}:",
        f"  {i18n.get('autoparse-detail-runs')}: {company.total_runs}",
        f"  {i18n.get('autoparse-detail-vacancies')}: {vacancies_count}",
        f"  {i18n.get('autoparse-detail-last-run')}: {last_run}",
    ]
    if autorespond_global:
        ar_on = i18n.get("yes") if company.autorespond_enabled else i18n.get("no")
        mode_key = (
            "autorespond-mode-title-only"
            if company.autorespond_keyword_mode == "title_only"
            else "autorespond-mode-title-keywords"
        )
        lim = company.autorespond_max_per_run
        lim_s = i18n.get("autorespond-limit-all") if lim < 0 else str(lim)
        fb = f"{company.autorespond_resume_id[:8]}…" if company.autorespond_resume_id else "—"
        lines.extend(
            [
                "",
                f"<b>{i18n.get('autorespond-section-title')}</b>",
                f"{i18n.get('autorespond-detail-enabled')}: {ar_on}",
                f"{i18n.get('autorespond-detail-threshold')}: {company.autorespond_min_compat}%",
                f"{i18n.get('autorespond-detail-mode')}: {i18n.get(mode_key)}",
                f"{i18n.get('autorespond-detail-limit')}: {lim_s}",
                f"{i18n.get('autorespond-detail-resume-explain')}",
                f"{i18n.get('autorespond-detail-resume-fallback-id', fallback=fb)}",
            ]
        )
        if autorespond_task_enabled is False:
            lines.append(i18n.get("autorespond-worker-disabled-hint"))
    return "\n".join(lines)


async def should_show_run_now(
    session: AsyncSession,
    company: AutoparseCompany,
    user: User,
) -> bool:
    if user.is_admin:
        return company.is_enabled
    if not company.is_enabled:
        return False
    settings_repo = AppSettingRepository(session)
    interval_hours = int(await settings_repo.get_value("autoparse_interval_hours", default=6))
    if company.last_parsed_at is None:
        return True
    elapsed = datetime.now(UTC).replace(tzinfo=None) - company.last_parsed_at
    return elapsed > timedelta(hours=interval_hours)


async def user_has_hh_browser_session(session: AsyncSession, user_id: int) -> bool:
    hh_repo = HhLinkedAccountRepository(session)
    accs = await hh_repo.list_active_for_user(user_id)
    return any(a.browser_storage_enc for a in accs)


async def build_company_detail_view(
    session: AsyncSession,
    *,
    company: AutoparseCompany,
    user: User,
    i18n: I18nContext,
    autorespond_global: bool = True,
    autorespond_task_enabled: bool,
) -> AutoparseCompanyDetailView:
    from src.repositories.autoparse import AutoparsedVacancyRepository

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancies_count = await vacancy_repo.count_by_company(company.id)
    show_run_now = await should_show_run_now(session, company, user)
    show_sync = await user_has_hh_browser_session(session, user.id)
    text = format_company_detail(
        company,
        vacancies_count,
        i18n,
        autorespond_global=autorespond_global,
        autorespond_task_enabled=autorespond_task_enabled,
    )
    return AutoparseCompanyDetailView(
        text=text,
        vacancies_count=vacancies_count,
        show_run_now=show_run_now,
        show_show_now=(vacancies_count > 0),
        show_sync_negotiations=show_sync,
        autorespond_task_enabled=autorespond_task_enabled,
    )
