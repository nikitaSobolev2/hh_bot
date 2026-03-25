"""Submit vacancy respond via site XHR POST /applicant/vacancy_response/popup (same as Magritte popup).

Uses page.evaluate(fetch + FormData) so the request runs in the tab origin with session cookies.
See docs/hhinside.md for captured multipart fields."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.core.logging import get_logger
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult

logger = get_logger(__name__)

_POPUP_PATH = "/applicant/vacancy_response/popup"
_LOG_BODY_MAX = 1200
_RAW_BODY_LOG_MAX = 64 * 1024  # cap full response in logs (ops / self-hosted)

_VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)", re.IGNORECASE)
_XSRF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'name="_xsrf"\s+value="([^"]+)"'),
    re.compile(r"name='_xsrf'\s+value='([^']+)'"),
    re.compile(r'name="_xsrf"\s+value=\'([^\']+)\''),
    re.compile(
        r'<meta[^>]+name=["\']_xsrf["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(r'"xsrf"\s*:\s*"([^"]+)"'),
    re.compile(r'"xsrfToken"\s*:\s*"([^"]+)"'),
    re.compile(r'"_xsrf"\s*:\s*"([^"]+)"'),
)


def parse_vacancy_id_from_url(vacancy_url: str) -> str | None:
    m = _VACANCY_ID_RE.search(vacancy_url or "")
    return m.group(1) if m else None


def hhtm_from_for_popup(vacancy_url: str) -> str:
    q = parse_qs(urlparse(vacancy_url).query)
    v = (q.get("hhtmFrom") or [None])[0]
    if v:
        return str(v)
    return "vacancy_search_list"


def extract_xsrf_token(html: str) -> str | None:
    for pat in _XSRF_PATTERNS:
        m = pat.search(html)
        if m and m.group(1):
            return m.group(1).strip()
    return None


def _truncate_for_log(s: str, max_len: int = _LOG_BODY_MAX) -> str:
    s = (s or "").replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _cap_raw_body_for_log(text: str) -> tuple[str, int, bool]:
    """Return (capped_text, original_len, truncated)."""
    raw = text or ""
    n = len(raw)
    if n <= _RAW_BODY_LOG_MAX:
        return raw, n, False
    return raw[:_RAW_BODY_LOG_MAX], n, True


def map_popup_json_to_apply_result(data: dict[str, Any]) -> ApplyResult | None:
    """Return terminal ApplyResult or None if legacy UI might still work."""
    success_raw = data.get("success")
    success = str(success_raw).lower() in ("true", "1", "yes")

    if success:
        return ApplyResult(outcome=ApplyOutcome.SUCCESS, detail="popup_api")

    extra = data.get("requiredAdditionalData")
    if isinstance(extra, list) and len(extra) > 0:
        return ApplyResult(
            outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
            detail=f"required_additional_data:{extra}",
        )

    errs = data.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0] if isinstance(errs[0], dict) else {}
        msg = str(first.get("value") or first.get("message") or errs[0])[:500]
        low = msg.lower()
        if "уже" in msg or "already" in low or ("отклик" in msg and "есть" in msg):
            return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED, detail="popup_api_duplicate")
        return ApplyResult(outcome=ApplyOutcome.ERROR, detail=f"popup_api:{msg[:200]}")

    err = data.get("error") or data.get("message")
    if err:
        return ApplyResult(outcome=ApplyOutcome.ERROR, detail=f"popup_api:{str(err)[:300]}")

    return None


def try_apply_via_popup(
    page: Any,
    vacancy_url: str,
    resume_hash: str,
    log_user_id: int | None = None,
    letter: str = "",
) -> ApplyResult | None:
    """POST vacancy_response/popup via in-page fetch. Returns None to fall back to modal UI."""
    vacancy_id = parse_vacancy_id_from_url(vacancy_url)
    if not vacancy_id:
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            reason="no_vacancy_id_in_url",
        )
        return None

    try:
        html = page.content()
    except Exception as exc:
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            reason="page_content_failed",
            error=str(exc)[:200],
        )
        return None

    xsrf = extract_xsrf_token(html)
    if not xsrf:
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            reason="xsrf_not_found",
        )
        return None

    hhtm_from = hhtm_from_for_popup(vacancy_url)
    letter = letter or ""

    js = f"""
    async (args) => {{
        const fd = new FormData();
        fd.append('_xsrf', args.xsrf);
        fd.append('vacancy_id', args.vacancy_id);
        fd.append('resume_hash', args.resume_hash);
        fd.append('ignore_postponed', 'true');
        fd.append('incomplete', 'false');
        fd.append('mark_applicant_visible_in_vacancy_country', 'false');
        fd.append('country_ids', '[]');
        fd.append('letter', args.letter);
        fd.append('lux', 'true');
        fd.append('withoutTest', 'no');
        fd.append('hhtmFromLabel', '');
        fd.append('hhtmSourceLabel', '');
        const r = await fetch('{_POPUP_PATH}', {{
            method: 'POST',
            body: fd,
            credentials: 'include',
            headers: {{
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
                'X-Xsrftoken': args.xsrf,
                'X-hhtmSource': 'vacancy',
                'X-hhtmFrom': args.hhtm_from,
            }},
        }});
        const text = await r.text();
        return {{ ok: r.ok, status: r.status, text: text }};
    }}
    """

    try:
        raw = page.evaluate(
            js,
            {
                "xsrf": xsrf,
                "vacancy_id": vacancy_id,
                "resume_hash": resume_hash,
                "letter": letter,
                "hhtm_from": hhtm_from,
            },
        )
    except Exception as exc:
        logger.info(
            "vacancy_popup_failed",
            log_user_id=log_user_id,
            step="evaluate_fetch",
            error=str(exc)[:300],
        )
        return None

    if not isinstance(raw, dict):
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            reason="unexpected_evaluate_result",
        )
        return None

    status = int(raw.get("status") or 0)
    text = str(raw.get("text") or "")
    ok = bool(raw.get("ok"))

    if not text.strip():
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            vacancy_id=vacancy_id,
            reason="empty_response_body",
            http_status=status,
            ok=ok,
        )
        return None

    raw_body, raw_len, truncated = _cap_raw_body_for_log(text)
    logger.info(
        "vacancy_popup_raw_response",
        log_user_id=log_user_id,
        vacancy_id=vacancy_id,
        http_status=status,
        ok=ok,
        raw_len=raw_len,
        truncated=truncated,
        raw_body=raw_body,
    )

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            vacancy_id=vacancy_id,
            reason="response_not_json",
            body_preview=_truncate_for_log(text, 400),
        )
        return None

    if not isinstance(data, dict):
        return None

    logger.info(
        "vacancy_popup_json_parsed",
        log_user_id=log_user_id,
        vacancy_id=vacancy_id,
        parsed_keys=sorted(data.keys()),
        success_field=repr(data.get("success")),
    )

    mapped = map_popup_json_to_apply_result(data)
    if mapped is not None:
        return mapped

    # 200 OK but unknown shape — let legacy modal flow try.
    if ok and status == 200:
        logger.info(
            "vacancy_popup_skip",
            log_user_id=log_user_id,
            reason="unmapped_json_200",
            body_preview=_truncate_for_log(json.dumps(data, ensure_ascii=False), 400),
        )
        return None

    return None
