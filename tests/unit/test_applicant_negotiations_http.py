"""Tests for applicant negotiations HTML parsing."""

from unittest.mock import patch

from src.services.hh_ui.applicant_negotiations_http import (
    fetch_all_negotiation_vacancy_cards,
    fetch_all_negotiation_vacancy_ids,
    parse_negotiation_vacancy_cards_from_html,
    parse_negotiation_vacancy_ids_from_html,
)
from src.services.hh_ui.config import HhUiApplyConfig


def test_parse_negotiation_vacancy_ids_from_item_and_href():
    html = """
    <div data-qa="negotiations-item">
      <a href="https://izhevsk.hh.ru/vacancy/12345?query=1">Title</a>
    </div>
    """
    ids = parse_negotiation_vacancy_ids_from_html(html)
    assert ids == {"12345"}


def test_parse_negotiation_vacancy_ids_fallback_regex():
    html = '<a href="/vacancy/999999">x</a>'
    ids = parse_negotiation_vacancy_ids_from_html(html)
    assert ids == {"999999"}


def test_parse_negotiation_vacancy_ids_from_data_attribute():
    html = """
    <main>
    <div data-qa="negotiations-item" data-vacancy-id="131309245">
      <span>No link</span>
    </div>
    </main>
    """
    ids = parse_negotiation_vacancy_ids_from_html(html)
    assert "131309245" in ids


def test_parse_negotiation_vacancy_ids_from_embedded_json():
    html = """
    <main><script type="application/json">{"items":[{"vacancyId":"131267558"}]}</script></main>
    """
    ids = parse_negotiation_vacancy_ids_from_html(html)
    assert "131267558" in ids


def test_parse_negotiation_vacancy_cards_from_item_response_link():
    html = """
    <main>
      <div data-qa="negotiations-item">
        <a href="/employer/80?hhtmFrom=negotiation_list">Company</a>
        <span data-qa="negotiations-item-vacancy">Backend Developer</span>
        <div data-qa="negotiations-item-company">Acme</div>
        <a
          data-qa="vacancy-serp__vacancy_response"
          href="/applicant/vacancy_response?vacancyId=123456&employerId=80"
        >Respond</a>
      </div>
    </main>
    """
    cards, all_ids = parse_negotiation_vacancy_cards_from_html(
        html,
        "https://izhevsk.hh.ru/applicant/negotiations",
    )

    assert all_ids == {"123456"}
    assert cards == {
        "123456": {
            "hh_vacancy_id": "123456",
            "url": "https://hh.ru/vacancy/123456",
            "title": "Backend Developer",
            "company_name": "Acme",
            "company_url": "https://izhevsk.hh.ru/employer/80?hhtmFrom=negotiation_list",
        }
    }


def test_parse_negotiation_vacancy_cards_falls_back_to_page_id_order():
    html = """
    <main>
      <div data-qa="negotiations-item">
        <span data-qa="negotiations-item-vacancy">First vacancy</span>
        <div data-qa="negotiations-item-company">First company</div>
      </div>
      <div data-qa="negotiations-item">
        <span data-qa="negotiations-item-vacancy">Second vacancy</span>
        <div data-qa="negotiations-item-company">Second company</div>
      </div>
      <a href="/vacancy/111111">Hidden first id</a>
      <a href="/vacancy/222222">Hidden second id</a>
    </main>
    """
    cards, all_ids = parse_negotiation_vacancy_cards_from_html(html)

    assert all_ids == {"111111", "222222"}
    assert cards["111111"]["title"] == "First vacancy"
    assert cards["111111"]["company_name"] == "First company"
    assert cards["222222"]["title"] == "Second vacancy"
    assert cards["222222"]["company_name"] == "Second company"


def test_fetch_all_negotiation_vacancy_ids_sleeps_between_pages():
    cfg = HhUiApplyConfig(
        navigation_timeout_ms=5000,
        action_timeout_ms=2000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        headless=True,
        screenshot_on_error=False,
        use_popup_api=False,
    )

    with (
        patch(
            "src.services.hh_ui.applicant_negotiations_http.fetch_applicant_negotiations_html",
            side_effect=[
                ('<a href="/vacancy/111111">one</a>', None, "https://hh.ru/applicant/negotiations"),
                ('<a href="/vacancy/222222">two</a>', None, "https://hh.ru/applicant/negotiations?page=2"),
                ("", None, "https://hh.ru/applicant/negotiations?page=3"),
            ],
        ),
        patch("src.services.hh_ui.applicant_negotiations_http.time.sleep") as sleep_mock,
        patch(
            "src.services.hh_ui.applicant_negotiations_http.random.uniform",
            return_value=1.0,
        ) as uniform_mock,
    ):
        ids, err = fetch_all_negotiation_vacancy_ids({"cookies": []}, cfg, max_pages=5)

    assert err is None
    assert ids == {"111111", "222222"}
    assert uniform_mock.call_count == 2
    assert sleep_mock.call_count == 2
    assert [call.args[0] for call in sleep_mock.call_args_list] == [1.0, 1.0]


def test_fetch_all_negotiation_vacancy_cards_returns_cards_and_ids():
    cfg = HhUiApplyConfig(
        navigation_timeout_ms=5000,
        action_timeout_ms=2000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        headless=True,
        screenshot_on_error=False,
        use_popup_api=False,
    )

    html = """
    <main>
      <div data-qa="negotiations-item">
        <span data-qa="negotiations-item-vacancy">Python Engineer</span>
        <div data-qa="negotiations-item-company">Example LLC</div>
        <a href="/applicant/vacancy_response?vacancyId=555555">Respond</a>
      </div>
    </main>
    """

    with (
        patch(
            "src.services.hh_ui.applicant_negotiations_http.fetch_applicant_negotiations_html",
            side_effect=[(html, None, "https://hh.ru/applicant/negotiations"), ("", None, None)],
        ),
        patch("src.services.hh_ui.applicant_negotiations_http.time.sleep") as sleep_mock,
        patch(
            "src.services.hh_ui.applicant_negotiations_http.random.uniform",
            return_value=1.0,
        ),
    ):
        cards, ids, err = fetch_all_negotiation_vacancy_cards({"cookies": []}, cfg, max_pages=5)

    assert err is None
    assert ids == {"555555"}
    assert cards["555555"]["title"] == "Python Engineer"
    assert cards["555555"]["company_name"] == "Example LLC"
    sleep_mock.assert_called_once_with(1.0)
