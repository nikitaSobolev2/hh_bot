import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def sample_vacancy_html() -> str:
    return """
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/12345?from=search">
            Frontend Developer
        </a>
        <a data-qa="vacancy-serp__vacancy-employer" href="https://hh.ru/employer/100">
            Yandex
        </a>
        <span class="magritte-text___abc123">300 000 руб.</span>
        <div data-qa="vacancy-serp__tag-remote">Remote</div>
    </div>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/67890">
            Backend Engineer
        </a>
        <a data-qa="vacancy-serp__vacancy-employer" href="https://hh.ru/employer/200">
            VK
        </a>
    </div>
    """


@pytest.fixture
def sample_vacancy_page_html() -> str:
    return """
    <div data-qa="vacancy-description">
        We are looking for a developer with Python, Django, and PostgreSQL experience.
        Knowledge of Docker and CI/CD is a plus.
    </div>
    <div data-qa="skills-element"><div>Python</div></div>
    <div data-qa="skills-element"><div>Django</div></div>
    <div data-qa="skills-element"><div>PostgreSQL</div></div>
    <div data-qa="compensation-frequency-text">Monthly</div>
    <div data-qa="work-experience-text">3-6 years</div>
    <div data-qa="common-employment-text">Full-time</div>
    <div data-qa="work-schedule-by-days-text">5/2</div>
    <div data-qa="working-hours-text">8 hours</div>
    <div data-qa="work-formats-text">Remote</div>
    """


@pytest.fixture
def mock_openai_response() -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Python, Django, PostgreSQL, Docker, CI/CD"
    return response
