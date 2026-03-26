"""Shared fixtures for unit tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI chat completion response returning 5 keywords."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Python, Django, Flask, SQLAlchemy, PostgreSQL"
    return response


@pytest.fixture
def sample_vacancy_html() -> str:
    """Two vacancy cards: one Frontend (with salary + tags), one Backend (no salary)."""
    return """
    <html><body>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/12345?ref=test&hhtmFrom=search">Frontend Developer</a>
        <a data-qa="vacancy-serp__vacancy-employer"
           href="https://hh.ru/employer/100">Yandex</a>
        <span data-qa="vacancy-serp__tag-work-format">Remote</span>
        <span class="magritte-text___salary">300 000 руб.</span>
    </div>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/67890">Backend Developer</a>
        <a data-qa="vacancy-serp__vacancy-employer"
           href="https://hh.ru/employer/200">Acme Corp</a>
    </div>
    </body></html>
    """


@pytest.fixture
def sample_vacancy_api_response() -> dict:
    """HH.ru API search response: two vacancies (Frontend 12345, Backend 67890)."""
    return {
        "items": [
            {
                "id": "12345",
                "name": "Frontend Developer",
                "alternate_url": "https://hh.ru/vacancy/12345",
                "employer": {"name": "Yandex", "alternate_url": "https://hh.ru/employer/100"},
                "salary": {"from": 300000, "to": None, "currency": "RUR"},
                "work_format": [{"id": "REMOTE", "name": "Remote"}],
                "schedule": {"id": "fullDay", "name": "Полный день"},
            },
            {
                "id": "67890",
                "name": "Backend Developer",
                "alternate_url": "https://hh.ru/vacancy/67890",
                "employer": {"name": "Acme Corp", "alternate_url": "https://hh.ru/employer/200"},
                "salary": None,
                "work_format": [],
                "schedule": None,
            },
        ],
        "found": 100,
        "pages": 5,
        "page": 0,
        "per_page": 100,
    }


@pytest.fixture
def sample_vacancy_page_html() -> str:
    """Full vacancy detail page with description, skills, and all detail fields."""
    return """
    <html><body>
    <div data-qa="vacancy-description">
        Python developer needed. Django experience required.
    </div>
    <div data-qa="skills-element"><div>Python</div></div>
    <div data-qa="skills-element"><div>Django</div></div>
    <div data-qa="skills-element"><div>PostgreSQL</div></div>
    <span data-qa="compensation-frequency-text">Monthly</span>
    <span data-qa="work-experience-text">3-6 years</span>
    <span data-qa="common-employment-text">Full-time</span>
    <span data-qa="work-schedule-by-days-text">5/2</span>
    <span data-qa="working-hours-text">8 hours</span>
    <span data-qa="work-formats-text">Remote</span>
    </body></html>
    """


@pytest.fixture
def vacancy_html_with_viewer_count() -> str:
    """Vacancy card whose only Magritte-text element is a viewer-count string (not salary)."""
    return """
    <html><body>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/11111">Some Vacancy</a>
        <span class="magritte-text___viewers">Сейчас смотрят 6 человек</span>
    </div>
    </body></html>
    """


@pytest.fixture
def vacancy_html_with_rating() -> str:
    """Vacancy card whose only Magritte-text element is a numeric rating (not salary)."""
    return """
    <html><body>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/22222">Some Vacancy</a>
        <span class="magritte-text___rating">2.6</span>
    </div>
    </body></html>
    """


@pytest.fixture
def vacancy_html_with_multi_span_salary() -> str:
    """Vacancy card with a salary split across multiple inner spans."""
    return """
    <html><body>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/33333">Some Vacancy</a>
        <span class="magritte-text___salary">
            <span>от</span><span>4 000</span><span>$</span><span>за месяц</span>
        </span>
    </div>
    </body></html>
    """


@pytest.fixture
def vacancy_page_html_with_work_format_prefix() -> str:
    """Vacancy page where work_formats and work_experience carry Russian label prefixes."""
    return """
    <html><body>
    <div data-qa="vacancy-description">Some description</div>
    <span data-qa="work-formats-text">Формат работы:удалённо</span>
    <span data-qa="work-experience-text">Опыт работы:1–3 года</span>
    </body></html>
    """


@pytest.fixture
def vacancy_page_html_with_compensation_frequency_prefix() -> str:
    """Vacancy page where compensation_frequency carries a Russian label prefix."""
    return """
    <html><body>
    <div data-qa="vacancy-description">Some description</div>
    <span data-qa="compensation-frequency-text">Оплата:ежемесячно</span>
    </body></html>
    """
