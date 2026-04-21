"""Tests for public HH vacancy API probe."""

from unittest.mock import patch

import httpx
import pytest
import respx

from src.services.hh.vacancy_public import (
    hh_vacancy_public_is_unavailable,
    hh_vacancy_public_preflight,
    vacancy_public_json_is_archived_or_hidden,
    vacancy_public_json_requires_employer_test,
)


@pytest.mark.asyncio
@respx.mock
async def test_unavailable_on_404():
    respx.get("https://api.hh.ru/vacancies/999").mock(return_value=httpx.Response(404))
    assert await hh_vacancy_public_is_unavailable("999") is True


@pytest.mark.asyncio
@respx.mock
async def test_unavailable_on_200_with_not_found_errors():
    body = {
        "description": "Not Found",
        "errors": [{"type": "not_found"}],
        "request_id": "x",
    }
    respx.get("https://api.hh.ru/vacancies/1").mock(return_value=httpx.Response(200, json=body))
    assert await hh_vacancy_public_is_unavailable("1") is True


@pytest.mark.asyncio
@respx.mock
async def test_available_on_200_with_vacancy():
    body = {"id": "123", "name": "Dev"}
    respx.get("https://api.hh.ru/vacancies/123").mock(return_value=httpx.Response(200, json=body))
    assert await hh_vacancy_public_is_unavailable("123") is False


@pytest.mark.asyncio
@respx.mock
async def test_not_unavailable_on_500():
    respx.get("https://api.hh.ru/vacancies/5").mock(return_value=httpx.Response(500, text="err"))
    assert await hh_vacancy_public_is_unavailable("5") is False


@pytest.mark.asyncio
@respx.mock
async def test_not_unavailable_on_429():
    respx.get("https://api.hh.ru/vacancies/42").mock(return_value=httpx.Response(429))
    assert await hh_vacancy_public_is_unavailable("42") is False


@pytest.mark.asyncio
async def test_invalid_id_returns_false():
    assert await hh_vacancy_public_is_unavailable("") is False
    assert await hh_vacancy_public_is_unavailable("abc") is False


def test_vacancy_public_json_archived_or_hidden_flags():
    assert vacancy_public_json_is_archived_or_hidden({"archived": True}) is True
    assert vacancy_public_json_is_archived_or_hidden({"hidden": True}) is True
    assert vacancy_public_json_is_archived_or_hidden({"archived": True, "hidden": False}) is True
    assert vacancy_public_json_is_archived_or_hidden({"archived": False, "hidden": True}) is True
    assert vacancy_public_json_is_archived_or_hidden({"archived": False, "hidden": False}) is False
    assert vacancy_public_json_is_archived_or_hidden({"id": "1"}) is False


def test_vacancy_public_json_requires_employer_test_flags():
    assert vacancy_public_json_requires_employer_test({"has_test": True}) is True
    assert vacancy_public_json_requires_employer_test({"test": {"required": True}}) is True
    assert (
        vacancy_public_json_requires_employer_test(
            {"has_test": True, "test": {"required": True}}
        )
        is True
    )
    assert vacancy_public_json_requires_employer_test({"has_test": False}) is False
    assert vacancy_public_json_requires_employer_test({"test": {"required": False}}) is False
    assert vacancy_public_json_requires_employer_test({"id": "1", "name": "x"}) is False


@pytest.mark.asyncio
@respx.mock
async def test_preflight_requires_test_on_200():
    body = {
        "id": "129569197",
        "name": "PHP",
        "has_test": True,
        "test": {"required": True},
    }
    respx.get("https://api.hh.ru/vacancies/129569197").mock(
        return_value=httpx.Response(200, json=body)
    )
    p = await hh_vacancy_public_preflight("129569197")
    assert p.unavailable is False
    assert p.requires_employer_test is True


@pytest.mark.asyncio
@respx.mock
async def test_preflight_unavailable_on_404_numeric_id():
    respx.get("https://api.hh.ru/vacancies/999001").mock(return_value=httpx.Response(404))
    p = await hh_vacancy_public_preflight("999001")
    assert p.unavailable is True
    assert p.requires_employer_test is False


@pytest.mark.asyncio
@respx.mock
async def test_preflight_unavailable_when_archived_true():
    body = {"id": "111", "name": "X", "archived": True, "hidden": False}
    respx.get("https://api.hh.ru/vacancies/111").mock(return_value=httpx.Response(200, json=body))
    p = await hh_vacancy_public_preflight("111")
    assert p.unavailable is True
    assert p.requires_employer_test is False
    assert await hh_vacancy_public_is_unavailable("111") is True


@pytest.mark.asyncio
@respx.mock
async def test_preflight_unavailable_when_hidden_true():
    body = {"id": "222", "name": "Y", "archived": False, "hidden": True}
    respx.get("https://api.hh.ru/vacancies/222").mock(return_value=httpx.Response(200, json=body))
    p = await hh_vacancy_public_preflight("222")
    assert p.unavailable is True
    assert p.requires_employer_test is False


@pytest.mark.asyncio
@respx.mock
async def test_preflight_403_retries_json_via_playwright_mock():
    respx.get("https://api.hh.ru/vacancies/777").mock(
        return_value=httpx.Response(
            403,
            json={"errors": [{"type": "forbidden"}]},
        )
    )
    body = {"id": "777", "name": "Role", "has_test": True, "test": {"required": True}}
    with patch(
        "src.services.hh.vacancy_public.fetch_public_hh_api_json_via_browser",
        return_value=body,
    ):
        p = await hh_vacancy_public_preflight("777")
    assert p.unavailable is False
    assert p.requires_employer_test is True


@pytest.mark.asyncio
@respx.mock
async def test_preflight_archived_before_employer_test():
    """Archived/hidden wins over has_test — same routing as closed vacancy (dislike)."""
    body = {
        "id": "333",
        "archived": True,
        "has_test": True,
        "test": {"required": True},
    }
    respx.get("https://api.hh.ru/vacancies/333").mock(return_value=httpx.Response(200, json=body))
    p = await hh_vacancy_public_preflight("333")
    assert p.unavailable is True
    assert p.requires_employer_test is False
