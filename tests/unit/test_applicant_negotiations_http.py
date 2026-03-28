"""Tests for applicant negotiations HTML parsing."""

from src.services.hh_ui.applicant_negotiations_http import parse_negotiation_vacancy_ids_from_html


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
