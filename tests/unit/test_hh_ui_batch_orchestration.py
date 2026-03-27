"""Batch UI apply wiring (mocked Playwright)."""

from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult
from src.services.hh_ui.vacancy_response_popup import POPUP_XSRF_ERROR_DETAIL
from src.services.hh_ui.runner import VacancyApplySpec, apply_to_vacancies_ui_batch


def test_apply_to_vacancies_ui_batch_single_launch(monkeypatch) -> None:
    """One sync_playwright context; inner launch path invoked once for multiple items."""
    calls: list[object] = []

    class FakePage:
        def goto(self, *a, **k):
            calls.append("goto")

    class FakeContext:
        def new_page(self):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

    class FakeChromium:
        def launch(self, **k):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePlaywright()

    def fake_flow(page, **kwargs):
        return ApplyResult(outcome=ApplyOutcome.SUCCESS)

    monkeypatch.setattr(
        "src.services.hh_ui.runner.sync_playwright",
        fake_sync_playwright,
    )
    monkeypatch.setattr(
        "src.services.hh_ui.runner._jitter",
        lambda c: None,
    )
    monkeypatch.setattr(
        "src.services.hh_ui.runner._apply_vacancy_flow_on_page",
        fake_flow,
    )

    cfg = HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=1000,
        action_timeout_ms=1000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=False,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )
    items = [
        VacancyApplySpec(
            autoparsed_vacancy_id=1,
            hh_vacancy_id="1",
            vacancy_url="https://hh.ru/vacancy/1",
            resume_hh_id="r1",
            cover_letter="",
        ),
        VacancyApplySpec(
            autoparsed_vacancy_id=2,
            hh_vacancy_id="2",
            vacancy_url="https://hh.ru/vacancy/2",
            resume_hh_id="r2",
            cover_letter="",
        ),
    ]
    out = apply_to_vacancies_ui_batch(
        storage_state={},
        items=items,
        config=cfg,
        max_retries=1,
    )
    assert len(out) == 2
    assert calls.count("goto") == 2


def test_batch_retries_once_on_retryable(monkeypatch) -> None:
    """Retry loop calls _apply_vacancy_flow twice when first returns ERROR."""
    attempts = {"n": 0}

    class FakePage:
        def goto(self, *a, **k):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

    class FakeChromium:
        def launch(self, **k):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePlaywright()

    def fake_flow(page, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return ApplyResult(outcome=ApplyOutcome.ERROR, detail="x")
        return ApplyResult(outcome=ApplyOutcome.SUCCESS)

    monkeypatch.setattr(
        "src.services.hh_ui.runner.sync_playwright",
        fake_sync_playwright,
    )
    monkeypatch.setattr("src.services.hh_ui.runner._jitter", lambda c: None)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.time.sleep",
        lambda s: None,
    )
    monkeypatch.setattr(
        "src.services.hh_ui.runner._apply_vacancy_flow_on_page",
        fake_flow,
    )

    cfg = HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=1000,
        action_timeout_ms=1000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=False,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )
    spec = VacancyApplySpec(
        autoparsed_vacancy_id=1,
        hh_vacancy_id="1",
        vacancy_url="https://hh.ru/vacancy/1",
        resume_hh_id="r1",
        cover_letter="",
    )
    out = apply_to_vacancies_ui_batch(
        storage_state={},
        items=[spec],
        config=cfg,
        max_retries=2,
        retry_initial_seconds=0.0,
        retry_delay_cap_seconds=1.0,
    )
    assert out[0][1].outcome == ApplyOutcome.SUCCESS
    assert attempts["n"] == 2


def test_apply_to_vacancies_ui_batch_on_item_done_order(monkeypatch) -> None:
    """on_item_done is invoked after each spec with the final ApplyResult."""
    done: list[tuple[int, str]] = []

    class FakePage:
        def goto(self, *a, **k):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

    class FakeChromium:
        def launch(self, **k):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePlaywright()

    def fake_flow(page, **kwargs):
        return ApplyResult(outcome=ApplyOutcome.SUCCESS)

    def on_done(spec, result):
        done.append((spec.autoparsed_vacancy_id, result.outcome.value))

    monkeypatch.setattr(
        "src.services.hh_ui.runner.sync_playwright",
        fake_sync_playwright,
    )
    monkeypatch.setattr("src.services.hh_ui.runner._jitter", lambda c: None)
    monkeypatch.setattr(
        "src.services.hh_ui.runner._apply_vacancy_flow_on_page",
        fake_flow,
    )

    cfg = HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=1000,
        action_timeout_ms=1000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=False,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )
    specs = [
        VacancyApplySpec(
            autoparsed_vacancy_id=1,
            hh_vacancy_id="1",
            vacancy_url="https://hh.ru/vacancy/1",
            resume_hh_id="r1",
            cover_letter="",
        ),
        VacancyApplySpec(
            autoparsed_vacancy_id=2,
            hh_vacancy_id="2",
            vacancy_url="https://hh.ru/vacancy/2",
            resume_hh_id="r2",
            cover_letter="",
        ),
    ]
    apply_to_vacancies_ui_batch(
        storage_state={},
        items=specs,
        config=cfg,
        max_retries=1,
        on_item_done=on_done,
    )
    assert done == [(1, "success"), (2, "success")]


def test_batch_xsrf_cooldown_exponential_between_items(monkeypatch) -> None:
    """After popup_api:xsrf_403, sleep 10s, 20s, ... (capped) before the next vacancy."""
    sleeps: list[float] = []

    class FakePage:
        def goto(self, *a, **k):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

    class FakeChromium:
        def launch(self, **k):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePlaywright()

    def fake_flow(page, **kwargs):
        return ApplyResult(outcome=ApplyOutcome.ERROR, detail=POPUP_XSRF_ERROR_DETAIL)

    monkeypatch.setattr(
        "src.services.hh_ui.runner.sync_playwright",
        fake_sync_playwright,
    )
    monkeypatch.setattr("src.services.hh_ui.runner._jitter", lambda c: None)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    monkeypatch.setattr(
        "src.services.hh_ui.runner._apply_vacancy_flow_on_page",
        fake_flow,
    )

    cfg = HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=1000,
        action_timeout_ms=1000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=False,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )
    specs = [
        VacancyApplySpec(
            autoparsed_vacancy_id=i,
            hh_vacancy_id=str(i),
            vacancy_url=f"https://hh.ru/vacancy/{i}",
            resume_hh_id="r1",
            cover_letter="",
        )
        for i in range(1, 4)
    ]
    apply_to_vacancies_ui_batch(
        storage_state={},
        items=specs,
        config=cfg,
        max_retries=1,
        xsrf_cooldown_initial_seconds=10.0,
        xsrf_cooldown_cap_seconds=300.0,
    )
    assert sleeps == [10.0, 20.0]


def test_batch_xsrf_cooldown_resets_after_non_xsrf(monkeypatch) -> None:
    sleeps: list[float] = []

    class FakePage:
        def goto(self, *a, **k):
            pass

    class FakeContext:
        def new_page(self):
            return FakePage()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeBrowser:
        def new_context(self, **k):
            return FakeContext()

    class FakeChromium:
        def launch(self, **k):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self) -> None:
            self.chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_sync_playwright():
        return FakePlaywright()

    n = {"i": 0}

    def fake_flow(page, **kwargs):
        n["i"] += 1
        if n["i"] in (1, 3):
            return ApplyResult(outcome=ApplyOutcome.ERROR, detail=POPUP_XSRF_ERROR_DETAIL)
        return ApplyResult(outcome=ApplyOutcome.SUCCESS)

    monkeypatch.setattr(
        "src.services.hh_ui.runner.sync_playwright",
        fake_sync_playwright,
    )
    monkeypatch.setattr("src.services.hh_ui.runner._jitter", lambda c: None)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.time.sleep",
        lambda s: sleeps.append(float(s)),
    )
    monkeypatch.setattr(
        "src.services.hh_ui.runner._apply_vacancy_flow_on_page",
        fake_flow,
    )

    cfg = HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=1000,
        action_timeout_ms=1000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=False,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )
    specs = [
        VacancyApplySpec(
            autoparsed_vacancy_id=i,
            hh_vacancy_id=str(i),
            vacancy_url=f"https://hh.ru/vacancy/{i}",
            resume_hh_id="r1",
            cover_letter="",
        )
        for i in range(1, 5)
    ]
    apply_to_vacancies_ui_batch(
        storage_state={},
        items=specs,
        config=cfg,
        max_retries=1,
    )
    assert sleeps == [10.0, 10.0]
