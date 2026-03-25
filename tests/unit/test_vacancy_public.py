"""Tests for public HH vacancy API probe."""

import httpx
import pytest
import respx

from src.services.hh.vacancy_public import hh_vacancy_public_is_unavailable


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
