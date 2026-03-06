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
    </div>
    <div data-qa="vacancy-serp__vacancy">
        <a href="https://hh.ru/vacancy/67890">
            Backend Engineer
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
    """


@pytest.fixture
def mock_openai_response() -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Python, Django, PostgreSQL, Docker, CI/CD"
    return response
