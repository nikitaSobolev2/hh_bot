"""Low-level HeadHunter API HTTP calls (Bearer token)."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from src.config import settings

HH_API_BASE = "https://api.hh.ru"


class HhApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: dict[str, Any] | str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _merge_query(url: str, extra: dict[str, str]) -> str:
    p = urlparse(url)
    q = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(p.query, keep_blank_values=True).items()}
    for k, v in extra.items():
        q[k] = v
    flat = []
    for k, vals in q.items():
        if isinstance(vals, list):
            for v in vals:
                flat.append((k, v))
        else:
            flat.append((k, vals))
    new_query = urlencode(flat, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))


class HhApiClient:
    def __init__(self, access_token: str) -> None:
        self._access_token = access_token
        self._ua = settings.hh_user_agent

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "HH-User-Agent": self._ua,
            "User-Agent": self._ua,
            "Accept": "application/json",
        }

    async def get_me(self) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{HH_API_BASE}/me", headers=self._headers(), timeout=30.0)
            if r.status_code >= 400:
                raise HhApiError(
                    f"GET /me failed: {r.status_code}",
                    status_code=r.status_code,
                    body=_safe_json(r),
                )
            return r.json()

    async def get_resumes_mine(self, *, page: int = 0, per_page: int = 20) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{HH_API_BASE}/resumes/mine",
                headers=self._headers(),
                params={"page": page, "per_page": per_page},
                timeout=30.0,
            )
            if r.status_code >= 400:
                raise HhApiError(
                    f"GET /resumes/mine failed: {r.status_code}",
                    status_code=r.status_code,
                    body=_safe_json(r),
                )
            return r.json()

    async def get_vacancy(self, vacancy_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{HH_API_BASE}/vacancies/{vacancy_id}",
                headers=self._headers(),
                timeout=30.0,
            )
            if r.status_code >= 400:
                raise HhApiError(
                    f"GET /vacancies failed: {r.status_code}",
                    status_code=r.status_code,
                    body=_safe_json(r),
                )
            return r.json()

    async def request_action_url(
        self,
        url: str,
        *,
        method: str = "POST",
        form: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | str]:
        """Call a full or relative URL returned by vacancy `negotiations_actions`."""
        if url.startswith("/"):
            url = f"{HH_API_BASE}{url}"
        form = form or {}
        async with httpx.AsyncClient() as client:
            m = method.upper()
            if m == "GET":
                full = _merge_query(url, form) if form else url
                r = await client.get(full, headers=self._headers(), timeout=60.0)
            else:
                r = await client.request(
                    m,
                    url,
                    headers={**self._headers(), "Content-Type": "application/x-www-form-urlencoded"},
                    data=form,
                    timeout=60.0,
                )
            payload = _safe_json(r)
            if r.status_code >= 400:
                raise HhApiError(
                    f"negotiation action failed: {r.status_code}",
                    status_code=r.status_code,
                    body=payload,
                )
            return r.status_code, payload if isinstance(payload, dict) else {"raw": payload}


def _safe_json(r: httpx.Response) -> dict[str, Any] | str:
    try:
        return r.json()
    except Exception:
        return r.text


def pick_response_negotiation_action(vacancy_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the negotiations_action dict used to apply (отклик), or None."""
    actions = vacancy_payload.get("negotiations_actions") or vacancy_payload.get("actions") or []
    if not isinstance(actions, list):
        return None
    for a in actions:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("id", "")).lower()
        name = str(a.get("name", "")).lower()
        if "response" in aid or "отклик" in name or "response" in name:
            return a
    for a in actions:
        if isinstance(a, dict) and a.get("url"):
            return a
    return None


async def apply_to_vacancy_with_resume(
    client: HhApiClient,
    *,
    vacancy_id: str,
    resume_id: str,
    letter: str | None = None,
) -> tuple[int, dict[str, Any] | str]:
    vac = await client.get_vacancy(vacancy_id)
    action = pick_response_negotiation_action(vac)
    if not action:
        raise HhApiError("Vacancy has no negotiations_actions for applying", body=vac)
    url = action.get("url")
    if not url or not isinstance(url, str):
        raise HhApiError("Invalid negotiations_action: missing url", body=action)
    method = str(action.get("method", "POST")).upper()
    args = action.get("arguments") or []
    form: dict[str, str] = {"resume_id": resume_id, "vacancy_id": vacancy_id}
    if isinstance(args, list):
        for item in args:
            if isinstance(item, dict):
                k = item.get("id") or item.get("name")
                v = item.get("value")
                if k is not None and v is not None:
                    form[str(k)] = str(v)
    lt = (letter or "").strip()
    if lt:
        form["letter"] = lt
    status, body = await client.request_action_url(url, method=method, form=form)
    return status, body
