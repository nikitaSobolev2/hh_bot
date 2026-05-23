"""Parse and format AI output for keyword-integrated work experience duties."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.core.i18n import get_text

_JSON_OBJECT_RE = re.compile(
    r'\{\s*"work_experiences"\s*:\s*\[.*?\]\s*\}',
    re.DOTALL,
)


@dataclass(frozen=True)
class IntegratedWorkExperienceBlock:
    work_exp_id: int
    company_name: str
    title: str | None
    duties: list[str]


@dataclass(frozen=True)
class IntegratedDutiesResult:
    keywords_used: list[str]
    work_experiences: list[IntegratedWorkExperienceBlock]


def _strip_markdown_fences(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize_duties(raw_duties: Any) -> list[str]:
    if not isinstance(raw_duties, list):
        return []
    duties: list[str] = []
    for item in raw_duties:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        if cleaned.startswith("- "):
            cleaned = cleaned[2:].strip()
        elif cleaned.startswith("-"):
            cleaned = cleaned[1:].strip()
        if cleaned:
            duties.append(cleaned)
    return duties


def _parse_work_experience_blocks(
    blocks: Any,
    allowed_work_exp_ids: set[int],
) -> list[IntegratedWorkExperienceBlock]:
    if not isinstance(blocks, list):
        raise ValueError("work_experiences must be a list")

    parsed: list[IntegratedWorkExperienceBlock] = []
    seen_ids: set[int] = set()

    for block in blocks:
        if not isinstance(block, dict):
            continue
        raw_id = block.get("work_exp_id")
        if raw_id is None:
            continue
        try:
            work_exp_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid work_exp_id: {raw_id!r}") from exc

        if work_exp_id not in allowed_work_exp_ids:
            raise ValueError(f"Unknown work_exp_id: {work_exp_id}")
        if work_exp_id in seen_ids:
            raise ValueError(f"Duplicate work_exp_id: {work_exp_id}")

        duties = _normalize_duties(block.get("duties"))
        if not duties:
            raise ValueError(f"Empty duties for work_exp_id: {work_exp_id}")

        seen_ids.add(work_exp_id)
        parsed.append(
            IntegratedWorkExperienceBlock(
                work_exp_id=work_exp_id,
                company_name=str(block.get("company_name") or "").strip(),
                title=(str(block.get("title")).strip() if block.get("title") else None),
                duties=duties,
            )
        )

    missing = allowed_work_exp_ids - seen_ids
    if missing:
        raise ValueError(f"Missing work_exp_id blocks: {sorted(missing)}")

    return parsed


def parse_integrated_duties_response(
    raw: str,
    allowed_work_exp_ids: set[int],
) -> list[IntegratedWorkExperienceBlock]:
    """Parse AI JSON response into validated work experience duty blocks."""
    text = _strip_markdown_fences(raw)
    if not text:
        raise ValueError("Empty AI response")

    obj: dict[str, Any] | None = None
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            obj = loaded
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if match:
            try:
                loaded = json.loads(match.group(0))
                if isinstance(loaded, dict):
                    obj = loaded
            except json.JSONDecodeError:
                obj = None

    if obj is None:
        raise ValueError("Failed to parse integrated duties JSON")

    return _parse_work_experience_blocks(obj.get("work_experiences"), allowed_work_exp_ids)


def build_integrated_duties_payload(
    *,
    vacancy_title: str,
    keywords_used: list[str],
    blocks: list[IntegratedWorkExperienceBlock],
) -> dict[str, Any]:
    return {
        "vacancy_title": vacancy_title,
        "keywords_used": keywords_used,
        "work_experiences": [
            {
                "work_exp_id": block.work_exp_id,
                "company_name": block.company_name,
                "title": block.title,
                "duties": block.duties,
            }
            for block in blocks
        ],
    }


def payload_to_result(payload: dict[str, Any]) -> IntegratedDutiesResult:
    blocks = [
        IntegratedWorkExperienceBlock(
            work_exp_id=int(item["work_exp_id"]),
            company_name=str(item.get("company_name") or ""),
            title=(str(item["title"]).strip() if item.get("title") else None),
            duties=_normalize_duties(item.get("duties")),
        )
        for item in payload.get("work_experiences") or []
        if isinstance(item, dict)
    ]
    keywords = [
        str(kw).strip()
        for kw in payload.get("keywords_used") or []
        if isinstance(kw, str) and kw.strip()
    ]
    return IntegratedDutiesResult(keywords_used=keywords, work_experiences=blocks)


def format_integrated_duties_report(payload: dict[str, Any], locale: str = "ru") -> str:
    """Format stored integrated duties payload as HTML for Telegram."""
    result = payload_to_result(payload)
    lines = [
        get_text(
            "integrate-duties-report-header",
            locale,
            title=str(payload.get("vacancy_title") or "—"),
        )
    ]
    if result.keywords_used:
        keywords_line = get_text(
            "integrate-duties-report-keywords",
            locale,
            keywords=", ".join(result.keywords_used),
        )
        lines.append(keywords_line)

    for block in result.work_experiences:
        header = block.company_name or str(block.work_exp_id)
        if block.title:
            header = f"{header} ({block.title})"
        lines.append("")
        lines.append(get_text("integrate-duties-report-company", locale, company=header))
        for duty in block.duties:
            lines.append(f"• {duty}")

    return "\n".join(lines)


def duties_list_to_text(duties: list[str]) -> str:
    return "\n".join(f"- {duty}" for duty in duties)
