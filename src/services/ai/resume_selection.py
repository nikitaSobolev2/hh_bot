"""AI-assisted choice of HH resume id for autorespond (per vacancy)."""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.constants import AI_MAX_DESCRIPTION_LENGTH
from src.core.logging import get_logger
from src.models.autoparse import AutoparsedVacancy
from src.services.ai.client import AIClient
from src.services.ai.prompts import (
    build_resume_choice_system_prompt,
    build_resume_choice_user_content,
)

logger = get_logger(__name__)

_MAX_RESUMES = 12

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\"resume_id\"[^{}]*\}")


def normalize_hh_resume_cache_items(raw: list[Any] | None) -> list[dict[str, str]]:
    """Return up to _MAX_RESUMES items with string keys ``id`` and ``title`` from JSONB cache."""
    if not raw or not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for it in raw[:_MAX_RESUMES]:
        if not isinstance(it, dict):
            continue
        rid = it.get("id")
        if rid is None:
            continue
        title = str(it.get("title") or it.get("name") or "").strip()
        out.append({"id": str(rid).strip(), "title": title or str(rid)[:40]})
    return out


def parse_resume_id_from_llm(text: str, allowed_ids: set[str]) -> str | None:
    """Parse JSON ``{\"resume_id\": \"...\"}`` from model output; validate membership."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        m = _JSON_OBJECT_RE.search(raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None
    rid = obj.get("resume_id")
    if rid is None:
        return None
    s = str(rid).strip()
    if s in allowed_ids:
        return s
    return None


def fallback_resume_id(
    resume_items: list[dict[str, str]],
    stored_autorespond_resume_id: str | None,
) -> str:
    """Pick fallback when AI fails: stored id if valid, else first in list."""
    allowed = {x["id"] for x in resume_items}
    if stored_autorespond_resume_id and str(stored_autorespond_resume_id).strip() in allowed:
        return str(stored_autorespond_resume_id).strip()
    return resume_items[0]["id"]


async def choose_hh_resume_for_vacancy(
    ai_client: AIClient,
    vacancy: AutoparsedVacancy,
    resume_items: list[dict[str, str]],
    *,
    stored_autorespond_resume_id: str | None,
) -> str:
    """Pick one resume id for *vacancy* (call only when len(resume_items) >= 2)."""
    if len(resume_items) < 2:
        raise ValueError("choose_hh_resume_for_vacancy requires at least 2 resumes")
    allowed_ids = {x["id"] for x in resume_items}
    lines = [(x["id"], x["title"]) for x in resume_items]
    desc = (vacancy.description or "")[:AI_MAX_DESCRIPTION_LENGTH]
    user_content = build_resume_choice_user_content(
        vacancy.title or "",
        desc,
        lines,
    )
    try:
        raw = await ai_client.generate_text(
            user_content,
            system_prompt=build_resume_choice_system_prompt(),
            timeout=120,
            max_tokens=200,
            temperature=0.2,
        )
    except Exception as exc:
        logger.warning(
            "resume_choice_llm_failed",
            vacancy_id=vacancy.id,
            error=str(exc)[:300],
        )
        picked = fallback_resume_id(resume_items, stored_autorespond_resume_id)
        logger.info(
            "resume_choice_fallback",
            vacancy_id=vacancy.id,
            resume_id_prefix=picked[:12],
            reason="llm_error",
        )
        return picked
    parsed = parse_resume_id_from_llm(raw, allowed_ids)
    if parsed:
        logger.info(
            "resume_choice_ok",
            vacancy_id=vacancy.id,
            resume_id_prefix=parsed[:12],
        )
        return parsed
    picked = fallback_resume_id(resume_items, stored_autorespond_resume_id)
    logger.warning(
        "resume_choice_parse_fallback",
        vacancy_id=vacancy.id,
        resume_id_prefix=picked[:12],
        raw_preview=raw[:200],
    )
    return picked


async def resolve_resume_id_for_autorespond_vacancy(
    ai_client: AIClient | None,
    vacancy: AutoparsedVacancy,
    resume_items: list[dict[str, str]],
    *,
    stored_autorespond_resume_id: str | None,
) -> str | None:
    """Return resume id for this vacancy; no LLM when exactly one resume in *resume_items*."""
    if not resume_items:
        return None
    if len(resume_items) == 1:
        return resume_items[0]["id"]
    if ai_client is None:
        return fallback_resume_id(resume_items, stored_autorespond_resume_id)
    return await choose_hh_resume_for_vacancy(
        ai_client,
        vacancy,
        resume_items,
        stored_autorespond_resume_id=stored_autorespond_resume_id,
    )
