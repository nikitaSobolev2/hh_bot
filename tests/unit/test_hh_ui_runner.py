"""Tests for HH UI runner helpers (no real browser)."""

from unittest.mock import patch

from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.runner import (
    normalize_hh_vacancy_url,
    render_search_page_with_storage,
    vacancy_url_from_hh_id,
)


def test_vacancy_url_from_hh_id_numeric() -> None:
    assert vacancy_url_from_hh_id("12345") == "https://hh.ru/vacancy/12345"


def test_vacancy_url_from_hh_id_full_url() -> None:
    u = "https://hh.ru/vacancy/999"
    assert vacancy_url_from_hh_id(u) == u


def test_normalize_hh_vacancy_url_relative() -> None:
    assert normalize_hh_vacancy_url("/vacancy/1", "1") == "https://hh.ru/vacancy/1"


def test_normalize_hh_vacancy_url_fallback() -> None:
    assert normalize_hh_vacancy_url("", "42") == "https://hh.ru/vacancy/42"


def test_render_search_page_with_storage_scrolls_once_and_returns_html() -> None:
    class FakeLocator:
        def __init__(self, page, selector: str):
            self.page = page
            self.selector = selector

        @property
        def first(self):
            return self

        def wait_for(self, **kwargs) -> None:
            return None

        def count(self) -> int:
            if self.selector == '[data-qa="vacancy-serp__vacancy"]':
                return 20 if not self.page.scrolled else 50
            return 0

    class FakePage:
        def __init__(self):
            self.url = "https://hh.ru/search/vacancy"
            self.scrolled = False

        def goto(self, url: str, **kwargs) -> None:
            self.url = url

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def evaluate(self, script: str) -> None:
            self.scrolled = True

        def wait_for_timeout(self, ms: int) -> None:
            return None

        def content(self) -> str:
            return "<html><body>loaded</body></html>"

    class FakeContext:
        def __init__(self):
            self.page = FakePage()

        def new_page(self) -> FakePage:
            return self.page

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self):
            self.context_kwargs = None
            self.context = FakeContext()

        def new_context(self, **kwargs):
            self.context_kwargs = kwargs
            return self.context

        def close(self) -> None:
            return None

    class FakePlaywright:
        def __init__(self):
            self.browser = FakeBrowser()
            self.chromium = self

        def launch(self, **kwargs):
            return self.browser

    class FakeSyncPlaywright:
        def __enter__(self):
            self.playwright = FakePlaywright()
            return self.playwright

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    cfg = HhUiApplyConfig(
        navigation_timeout_ms=5000,
        action_timeout_ms=2000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        headless=True,
        screenshot_on_error=False,
        use_popup_api=False,
    )

    fake_sync_playwright = FakeSyncPlaywright()
    with patch("src.services.hh_ui.runner.sync_playwright", return_value=fake_sync_playwright):
        result = render_search_page_with_storage(
            storage_state={"cookies": []},
            config=cfg,
            url="https://hh.ru/search/vacancy?text=python",
        )

    assert result.html == "<html><body>loaded</body></html>"
    assert result.final_url == "https://hh.ru/search/vacancy?text=python"
    assert result.cards_before_scroll == 20
    assert result.cards_after_scroll == 50


def test_render_search_page_with_storage_skips_scroll_when_page_is_full() -> None:
    class FakeLocator:
        def __init__(self, page, selector: str):
            self.page = page
            self.selector = selector

        @property
        def first(self):
            return self

        def wait_for(self, **kwargs) -> None:
            return None

        def count(self) -> int:
            if self.selector == '[data-qa="vacancy-serp__vacancy"]':
                return 50
            return 0

    class FakePage:
        def __init__(self):
            self.url = "https://hh.ru/search/vacancy"
            self.scroll_calls = 0

        def goto(self, url: str, **kwargs) -> None:
            self.url = url

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        def evaluate(self, script: str) -> None:
            self.scroll_calls += 1

        def wait_for_timeout(self, ms: int) -> None:
            return None

        def content(self) -> str:
            return "<html><body>loaded</body></html>"

    class FakeContext:
        def __init__(self):
            self.page = FakePage()

        def new_page(self) -> FakePage:
            return self.page

        def close(self) -> None:
            return None

    class FakeBrowser:
        def __init__(self):
            self.context_kwargs = None
            self.context = FakeContext()

        def new_context(self, **kwargs):
            self.context_kwargs = kwargs
            return self.context

        def close(self) -> None:
            return None

    class FakePlaywright:
        def __init__(self):
            self.browser = FakeBrowser()
            self.chromium = self

        def launch(self, **kwargs):
            return self.browser

    class FakeSyncPlaywright:
        def __enter__(self):
            self.playwright = FakePlaywright()
            return self.playwright

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    cfg = HhUiApplyConfig(
        navigation_timeout_ms=5000,
        action_timeout_ms=2000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        headless=True,
        screenshot_on_error=False,
        use_popup_api=False,
    )

    fake_sync_playwright = FakeSyncPlaywright()
    with patch("src.services.hh_ui.runner.sync_playwright", return_value=fake_sync_playwright):
        result = render_search_page_with_storage(
            storage_state={"cookies": []},
            config=cfg,
            url="https://hh.ru/search/vacancy?text=python",
        )

    assert result.html == "<html><body>loaded</body></html>"
    assert result.final_url == "https://hh.ru/search/vacancy?text=python"
    assert result.cards_before_scroll == 50
    assert result.cards_after_scroll == 50
    assert fake_sync_playwright.playwright.browser.context.page.scroll_calls == 0
