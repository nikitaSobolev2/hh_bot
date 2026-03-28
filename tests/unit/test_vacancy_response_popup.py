"""Tests for HH vacancy_response/popup helpers."""

from src.services.hh_ui.outcomes import ApplyOutcome
from src.services.hh_ui.vacancy_response_popup import (
    POPUP_XSRF_ERROR_DETAIL,
    _cap_raw_body_for_log,
    _popup_json_indicates_xsrf_error,
    _popup_post_url,
    build_popup_apply_curl_command,
    extract_xsrf_for_popup,
    extract_xsrf_token,
    extract_xsrf_token_from_dom,
    map_popup_json_to_apply_result,
    pick_xsrf_from_cookie_list,
    probe_xsrf_light_with_source,
    try_apply_via_popup,
)


def test_cap_raw_body_for_log_truncates_at_64k():
    long = "x" * (64 * 1024 + 100)
    capped, n, truncated = _cap_raw_body_for_log(long)
    assert n == 64 * 1024 + 100
    assert truncated is True
    assert len(capped) == 64 * 1024


def test_cap_raw_body_for_log_no_truncation():
    s = '{"a": 1}'
    capped, n, truncated = _cap_raw_body_for_log(s)
    assert capped == s
    assert n == len(s)
    assert truncated is False


def test_map_popup_errors_value_unknown_still_error():
    """errors[].value \"unknown\" is not the same as top-level error \"unknown\"."""
    data = {"success": False, "errors": [{"value": "unknown"}]}
    r = map_popup_json_to_apply_result(data)
    assert r is not None
    assert r.outcome == ApplyOutcome.ERROR
    assert "unknown" in (r.detail or "")


def test_map_popup_top_level_error_unknown():
    r = map_popup_json_to_apply_result({"error": "unknown"})
    assert r is not None
    assert r.outcome == ApplyOutcome.VACANCY_UNAVAILABLE
    assert r.detail == "popup_api:unknown"


def test_map_popup_top_level_error_test_required():
    r = map_popup_json_to_apply_result({"error": "test-required"})
    assert r is not None
    assert r.outcome == ApplyOutcome.EMPLOYER_QUESTIONS
    assert r.detail == "popup_api:test_required"


def test_map_popup_top_level_error_already_applied_is_already_responded():
    """HH sends ``{"error":"alreadyApplied"}``; must persist as success path, not generic error."""
    r = map_popup_json_to_apply_result({"error": "alreadyApplied"})
    assert r is not None
    assert r.outcome == ApplyOutcome.ALREADY_RESPONDED
    assert r.detail == "popup_api:alreadyApplied"


def test_map_popup_errors_type_not_found():
    r = map_popup_json_to_apply_result(
        {
            "description": "Not Found",
            "errors": [{"type": "not_found"}],
            "request_id": "x",
        }
    )
    assert r is not None
    assert r.outcome == ApplyOutcome.VACANCY_UNAVAILABLE
    assert r.detail == "popup_api:not_found"


def test_popup_post_url():
    assert _popup_post_url("https://izhevsk.hh.ru/vacancy/1") == (
        "https://izhevsk.hh.ru/applicant/vacancy_response/popup"
    )


def test_build_popup_apply_curl_command_shape():
    url = "https://hh.ru/vacancy/123"
    post = "https://hh.ru/applicant/vacancy_response/popup"
    curl = build_popup_apply_curl_command(
        vacancy_url=url,
        post_url=post,
        cookie_header="a=b; c=d",
        xsrf="tok",
        vacancy_id="123",
        resume_hash="resumehash",
        letter="hi",
        hhtm_from="vacancy_search_list",
    )
    assert "curl" in curl
    assert post in curl
    assert "Cookie: a=b; c=d" in curl
    assert "X-Xsrftoken: tok" in curl or "X-Xsrftoken" in curl
    assert "-F" in curl
    assert "vacancy_id=123" in curl.replace("'", "")


def test_popup_json_indicates_xsrf_error_errorpage():
    assert _popup_json_indicates_xsrf_error(
        {"errorPage": {"xsrfError": True}, "success": False}
    )


def test_popup_json_indicates_xsrf_error_top_level():
    assert _popup_json_indicates_xsrf_error({"xsrfError": True})


def test_popup_json_indicates_xsrf_error_negative():
    assert not _popup_json_indicates_xsrf_error({"success": False, "errors": []})


def test_map_popup_json_xsrf_error_shape_returns_none():
    """map_popup_json_to_apply_result does not map HH xsrf error JSON; try_apply_via_popup handles it."""
    r = map_popup_json_to_apply_result(
        {"isLightPage": True, "errorPage": {"xsrfError": True, "_xsrf": None}}
    )
    assert r is None


def test_extract_xsrf_token_from_dom_reads_input():
    class P:
        def evaluate(self, _script: str):
            return "abc123"

    assert extract_xsrf_token_from_dom(P()) == "abc123"


def test_extract_xsrf_for_popup_prefers_dom_over_html():
    class P:
        def __init__(self):
            self.content_called = False

        def evaluate(self, _script: str):
            return "from_dom"

        def content(self):
            self.content_called = True
            return '<input name="_xsrf" value="from_html" />'

    p = P()
    assert extract_xsrf_for_popup(p) == "from_dom"
    assert p.content_called is False


def test_extract_xsrf_for_popup_falls_back_to_html():
    class P:
        def evaluate(self, _script: str):
            return None

        def content(self):
            return '<input name="_xsrf" value="from_html" />'

    p = P()
    assert extract_xsrf_for_popup(p) == extract_xsrf_token(p.content())


def test_pick_xsrf_from_cookie_list_subdomain():
    cookies = [{"name": "_xsrf", "value": "tok1", "domain": ".hh.ru"}]
    assert (
        pick_xsrf_from_cookie_list(cookies, "https://izhevsk.hh.ru/vacancy/1") == "tok1"
    )


def test_pick_xsrf_from_cookie_list_host_only_domain():
    cookies = [{"name": "_xsrf", "value": "tok2", "domain": "hh.ru"}]
    assert pick_xsrf_from_cookie_list(cookies, "https://hh.ru/vacancy/1") == "tok2"


def test_pick_xsrf_from_cookie_list_rejects_domain_mismatch():
    cookies = [{"name": "_xsrf", "value": "x", "domain": ".other.ru"}]
    assert pick_xsrf_from_cookie_list(cookies, "https://hh.ru/vacancy/1") is None


def test_extract_xsrf_for_popup_falls_back_to_cookie_without_html_scan():
    class P:
        def __init__(self) -> None:
            self.content_called = False

        url = "https://hh.ru/vacancy/1"

        def evaluate(self, _script: str):
            return None

        @property
        def context(self):
            return self

        def cookies(self, urls=None):
            return [{"name": "_xsrf", "value": "from_cookie", "domain": ".hh.ru"}]

        def content(self):
            self.content_called = True
            return ""

    p = P()
    assert extract_xsrf_for_popup(p) == "from_cookie"
    assert p.content_called is False


def test_probe_xsrf_light_with_source_dom_wins():
    class P:
        def evaluate(self, _script: str):
            return "domtok"

        @property
        def context(self):
            return self

        def cookies(self, urls=None):
            return [{"name": "_xsrf", "value": "cook", "domain": ".hh.ru"}]

        url = "https://hh.ru/vacancy/1"

    tok, src = probe_xsrf_light_with_source(P())
    assert tok == "domtok"
    assert src == "dom"


def test_probe_xsrf_light_with_source_cookie_only():
    class P:
        def evaluate(self, _script: str):
            return None

        @property
        def context(self):
            return self

        def cookies(self, urls=None):
            return [{"name": "_xsrf", "value": "ck", "domain": ".hh.ru"}]

        url = "https://spb.hh.ru/vacancy/2"

    tok, src = probe_xsrf_light_with_source(P())
    assert tok == "ck"
    assert src == "cookie"


class _FakeCtx:
    def cookies(self, urls=None):
        return []


class _PageXsrfRetry:
    """First fetch 403 + errorPage.xsrfError; after goto second fetch succeeds."""

    def __init__(self) -> None:
        self.refreshes = 0
        self._seq = [
            "tok1",
            {
                "ok": False,
                "status": 403,
                "text": '{"errorPage":{"xsrfError":true}}',
            },
            "tok2",
            {"ok": True, "status": 200, "text": '{"success": true}'},
        ]
        self._i = 0

    @property
    def context(self):
        return _FakeCtx()

    def evaluate(self, _script: str, _arg=None):
        r = self._seq[self._i]
        self._i += 1
        return r

    def goto(self, _url, wait_until=None):
        self.refreshes += 1

    def wait_for_timeout(self, _ms: int) -> None:
        pass


def test_try_apply_via_popup_reloads_and_retries_on_xsrf_error_json():
    page = _PageXsrfRetry()
    r = try_apply_via_popup(
        page,
        "https://hh.ru/vacancy/123",
        "resumehash",
        log_user_id=1,
        letter="",
    )
    assert r is not None
    assert r.outcome == ApplyOutcome.SUCCESS
    assert page.refreshes == 1
    assert page._i == len(page._seq)


class _PageXsrfAlways403:
    """Every POST returns 403 + xsrf error JSON; refresh never fixes."""

    def __init__(self) -> None:
        self.refreshes = 0
        self._body = '{"errorPage":{"xsrfError":true},"errorCode":403}'
        self._eval_calls = 0

    @property
    def context(self):
        return _FakeCtx()

    def evaluate(self, _script: str, _arg=None):
        self._eval_calls += 1
        # Odd calls: DOM xsrf; even: popup fetch
        if self._eval_calls % 2 == 1:
            return "tok"
        return {"ok": False, "status": 403, "text": self._body}

    def goto(self, _url, wait_until=None):
        self.refreshes += 1

    def wait_for_timeout(self, _ms: int) -> None:
        pass


def test_try_apply_via_popup_persistent_xsrf_returns_error_not_none():
    page = _PageXsrfAlways403()
    r = try_apply_via_popup(
        page,
        "https://hh.ru/vacancy/999",
        "resumehash",
        log_user_id=1,
        letter="",
    )
    assert r is not None
    assert r.outcome == ApplyOutcome.ERROR
    assert r.detail == POPUP_XSRF_ERROR_DETAIL
    assert page.refreshes == 2
