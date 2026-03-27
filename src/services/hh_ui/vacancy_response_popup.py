"""Submit vacancy respond via site XHR POST /applicant/vacancy_response/popup (same as Magritte popup).

Uses page.evaluate(fetch + FormData) so the request runs in the tab origin with session cookies.
See docs/hhinside.md for captured multipart fields."""

from __future__ import annotations

import json
import re
import shlex
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


def extract_xsrf_token_from_dom(page: Any) -> str | None:
    """Read current _xsrf from the live DOM (preferred over scanning full HTML)."""
    try:
        token = page.evaluate(
            """() => {
                const i = document.querySelector('input[name="_xsrf"]');
                if (i && i.value) return String(i.value).trim();
                const m = document.querySelector('meta[name="_xsrf"]');
                if (m && m.content) return String(m.content).trim();
                return null;
            }"""
        )
        if token:
            return str(token).strip()
    except Exception:
        pass
    return None


def extract_xsrf_for_popup(page: Any) -> str | None:
    """DOM-first, then HTML patterns (avoids stale tokens from unrelated embedded markup)."""
    t = extract_xsrf_token_from_dom(page)
    if t:
        return t
    try:
        html = page.content()
    except Exception:
        return None
    return extract_xsrf_token(html)


def _popup_json_indicates_xsrf_error(data: dict[str, Any]) -> bool:
    ep = data.get("errorPage")
    if isinstance(ep, dict) and ep.get("xsrfError") is True:
        return True
    if data.get("xsrfError") is True:
        return True
    return False


def _reload_page_for_popup_xsrf_retry(page: Any, log_user_id: int | None) -> bool:
    """Reload after XSRF failure; return False if reload failed (caller should abort popup)."""
    try:
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        return True
    except Exception as exc:
        logger.info(
            "vacancy_popup_xsrf_retry_failed",
            log_user_id=log_user_id,
            error=str(exc)[:200],
        )
        return False


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


def _popup_post_url(vacancy_url: str) -> str:
    p = urlparse(vacancy_url or "")
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme}://{p.netloc}{_POPUP_PATH}"


def _cookie_header_for_page(page: Any, url: str) -> str | None:
    """Serialize Playwright cookies for curl ``Cookie:`` header (same session as in-page fetch)."""
    try:
        ctx = page.context
        cookies = ctx.cookies(urls=[url])
        if not cookies:
            cookies = ctx.cookies()
        if not cookies:
            return None
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    except Exception:
        return None


def build_popup_apply_curl_command(
    *,
    vacancy_url: str,
    post_url: str,
    cookie_header: str | None,
    xsrf: str,
    vacancy_id: str,
    resume_hash: str,
    letter: str,
    hhtm_from: str,
) -> str:
    """Single-line shell command equivalent to the in-page ``fetch`` (multipart ``-F``)."""
    parts: list[str] = ["curl", "-sS", "-X", "POST", shlex.quote(post_url)]
    if cookie_header:
        parts.extend(["-H", shlex.quote(f"Cookie: {cookie_header}")])
    parts.extend(
        [
            "-H",
            shlex.quote("X-Requested-With: XMLHttpRequest"),
            "-H",
            shlex.quote("Accept: application/json"),
            "-H",
            shlex.quote(f"X-Xsrftoken: {xsrf}"),
            "-H",
            shlex.quote("X-hhtmSource: vacancy"),
            "-H",
            shlex.quote(f"X-hhtmFrom: {hhtm_from}"),
            "-H",
            shlex.quote(f"Referer: {vacancy_url}"),
        ]
    )
    form_fields: list[tuple[str, str]] = [
        ("_xsrf", xsrf),
        ("vacancy_id", vacancy_id),
        ("resume_hash", resume_hash),
        ("ignore_postponed", "true"),
        ("incomplete", "false"),
        ("mark_applicant_visible_in_vacancy_country", "false"),
        ("country_ids", "[]"),
        ("letter", letter),
        ("lux", "true"),
        ("withoutTest", "no"),
        ("hhtmFromLabel", ""),
        ("hhtmSourceLabel", ""),
    ]
    for name, val in form_fields:
        parts.extend(["-F", shlex.quote(f"{name}={val}")])
    return " ".join(parts)


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
        for e in errs:
            if isinstance(e, dict) and e.get("type") == "not_found":
                return ApplyResult(
                    outcome=ApplyOutcome.VACANCY_UNAVAILABLE,
                    detail="popup_api:not_found",
                )
        first = errs[0] if isinstance(errs[0], dict) else {}
        msg = str(first.get("value") or first.get("message") or errs[0])[:500]
        low = msg.lower()
        if "уже" in msg or "already" in low or ("отклик" in msg and "есть" in msg):
            return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED, detail="popup_api_duplicate")
        return ApplyResult(outcome=ApplyOutcome.ERROR, detail=f"popup_api:{msg[:200]}")

    err = data.get("error") or data.get("message")
    if err:
        if str(err).strip().lower() == "unknown":
            return ApplyResult(
                outcome=ApplyOutcome.VACANCY_UNAVAILABLE,
                detail="popup_api:unknown",
            )
        return ApplyResult(outcome=ApplyOutcome.ERROR, detail=f"popup_api:{str(err)[:300]}")

    return None


_POPUP_FETCH_JS = """
    async (args) => {
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
        const r = await fetch('__POPUP_PATH__', {
            method: 'POST',
            body: fd,
            credentials: 'include',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
                'X-Xsrftoken': args.xsrf,
                'X-hhtmSource': 'vacancy',
                'X-hhtmFrom': args.hhtm_from,
            },
        });
        const text = await r.text();
        return { ok: r.ok, status: r.status, text: text };
    }
    """.replace("__POPUP_PATH__", _POPUP_PATH)


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

    hhtm_from = hhtm_from_for_popup(vacancy_url)
    letter = letter or ""
    post_url = _popup_post_url(vacancy_url)

    for attempt in range(2):
        xsrf = extract_xsrf_for_popup(page)
        if not xsrf:
            logger.info(
                "vacancy_popup_skip",
                log_user_id=log_user_id,
                reason="xsrf_not_found",
                attempt=attempt,
            )
            return None

        if post_url:
            cookie_header = _cookie_header_for_page(page, vacancy_url)
            curl_cmd = build_popup_apply_curl_command(
                vacancy_url=vacancy_url,
                post_url=post_url,
                cookie_header=cookie_header,
                xsrf=xsrf,
                vacancy_id=vacancy_id,
                resume_hash=resume_hash,
                letter=letter,
                hhtm_from=hhtm_from,
            )
            logger.info(
                "vacancy_popup_curl",
                log_user_id=log_user_id,
                vacancy_id=vacancy_id,
                post_url=post_url,
                cookie_included=cookie_header is not None,
                attempt=attempt,
                curl=curl_cmd,
            )

        try:
            raw = page.evaluate(
                _POPUP_FETCH_JS,
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
                attempt=attempt,
                error=str(exc)[:300],
            )
            return None

        if not isinstance(raw, dict):
            logger.info(
                "vacancy_popup_skip",
                log_user_id=log_user_id,
                reason="unexpected_evaluate_result",
                attempt=attempt,
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
                attempt=attempt,
            )
            if status == 403 and attempt == 0:
                logger.info(
                    "vacancy_popup_xsrf_retry",
                    log_user_id=log_user_id,
                    vacancy_id=vacancy_id,
                    attempt=attempt,
                    reason="empty_body_403",
                )
                if _reload_page_for_popup_xsrf_retry(page, log_user_id):
                    continue
                return None
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
            attempt=attempt,
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
                attempt=attempt,
            )
            if status == 403 and attempt == 0:
                logger.info(
                    "vacancy_popup_xsrf_retry",
                    log_user_id=log_user_id,
                    vacancy_id=vacancy_id,
                    attempt=attempt,
                    reason="non_json_403",
                )
                if _reload_page_for_popup_xsrf_retry(page, log_user_id):
                    continue
                return None
            return None

        if not isinstance(data, dict):
            return None

        logger.info(
            "vacancy_popup_json_parsed",
            log_user_id=log_user_id,
            vacancy_id=vacancy_id,
            parsed_keys=sorted(data.keys()),
            success_field=repr(data.get("success")),
            attempt=attempt,
        )

        if _popup_json_indicates_xsrf_error(data) and attempt == 0:
            logger.info(
                "vacancy_popup_xsrf_retry",
                log_user_id=log_user_id,
                vacancy_id=vacancy_id,
                attempt=attempt,
                reason="errorPage_xsrfError",
            )
            if _reload_page_for_popup_xsrf_retry(page, log_user_id):
                continue
            return None

        mapped = map_popup_json_to_apply_result(data)
        if mapped is not None:
            return mapped

        if ok and status == 200:
            logger.info(
                "vacancy_popup_skip",
                log_user_id=log_user_id,
                reason="unmapped_json_200",
                body_preview=_truncate_for_log(json.dumps(data, ensure_ascii=False), 400),
                attempt=attempt,
            )
            return None

        if status == 403 and attempt == 0:
            logger.info(
                "vacancy_popup_xsrf_retry",
                log_user_id=log_user_id,
                vacancy_id=vacancy_id,
                attempt=attempt,
                reason="http_403",
            )
            if _reload_page_for_popup_xsrf_retry(page, log_user_id):
                continue
            return None

        return None

    return None
