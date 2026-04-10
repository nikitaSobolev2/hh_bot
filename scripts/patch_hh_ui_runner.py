"""One-off migration tool: rewrite ``runner.py`` via string edits.

Do **not** run from CI or normal development workflows. Upstream changes to
``src/services/hh_ui/runner.py`` (line order, content) can make this script
corrupt the file. Use version control and review the diff manually after running.

Original purpose: extract ``_apply_vacancy_flow_on_page`` and add batch apply.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_patched_runner(text: str) -> str:
    text = text.replace(
        "from dataclasses import replace",
        "from dataclasses import dataclass, replace",
        1,
    )
    text = text.replace(
        "from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption",
        """from src.services.hh_ui.apply_retry import (
    apply_outcome_is_retryable,
    apply_outcome_is_terminal_no_retry,
    apply_retry_delay_seconds,
)
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption""",
        1,
    )

    start = text.index("def apply_to_vacancy_ui(")
    end = text.index("\ndef vacancy_url_from_hh_id")

    inner_start = text.index("            logger.info(\n                \"apply_to_vacancy_ui_step\",\n                log_user_id=log_user_id,\n                step=\"after_goto\",", start)
    inner_end = text.index(
        '            return _finish(ApplyResult(outcome=ApplyOutcome.SUCCESS), "success")', start
    ) + len('            return _finish(ApplyResult(outcome=ApplyOutcome.SUCCESS), "success")')

    inner_block = text[inner_start:inner_end]
    inner_lines = []
    for line in inner_block.splitlines():
        if line.startswith("            "):
            inner_lines.append("        " + line[12:])
        else:
            inner_lines.append(line)
    inner_body = "\n".join(inner_lines)

    prefix = '''def apply_to_vacancy_ui(
    *,
    storage_state: dict[str, Any],
    vacancy_url: str,
    resume_hh_id: str,
    config: HhUiApplyConfig,
    log_user_id: int | None = None,
    cover_letter: str = "",
) -> ApplyResult:
    """Open vacancy page and submit respond via UI."""
    safe_v = _safe_url_host_path(vacancy_url)
    resume_ref = resume_hh_id[:12] if resume_hh_id else None
    if not vacancy_url.startswith("https://"):
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            step="validate_url",
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail="invalid_vacancy_url",
        )
        return ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail="invalid_vacancy_url",
        )

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=config.headless,
                args=list(CHROMIUM_LAUNCH_ARGS),
            )
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            page.goto(
                vacancy_url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            _jitter(config)
            return _apply_vacancy_flow_on_page(
                page,
                vacancy_url=vacancy_url,
                resume_hh_id=resume_hh_id,
                config=config,
                log_user_id=log_user_id,
                cover_letter=cover_letter,
            )
        except PlaywrightTimeoutError as exc:
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=f"timeout:{exc}"[:200],
            )
            r = ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=f"timeout:{exc}",
            )
            _save_playwright_debug_disk(
                config,
                page=locals().get("page"),
                result=r,
                stem="playwright_timeout",
            )
            return r
        except Exception as exc:
            d = str(exc)[:500]
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=d[:200],
            )
            r = ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=d,
            )
            _save_playwright_debug_disk(
                config,
                page=locals().get("page"),
                result=r,
                stem="playwright_exception",
            )
            return r
        finally:
            dispose_sync_browser_context(context, browser)


def _apply_vacancy_flow_on_page(
    page: Any,
    *,
    vacancy_url: str,
    resume_hh_id: str,
    config: HhUiApplyConfig,
    log_user_id: int | None,
    cover_letter: str,
) -> ApplyResult:
    """Run respond flow after ``page`` has navigated to the vacancy (and optional jitter)."""
    safe_v = _safe_url_host_path(vacancy_url)
    resume_ref = resume_hh_id[:12] if resume_hh_id else None
    logger.info(
        "apply_to_vacancy_ui_step",
        log_user_id=log_user_id,
        step="after_goto",
        vacancy_url_safe=safe_v,
        resume_ref=resume_ref,
    )

    def _finish(result: ApplyResult, stem: str) -> ApplyResult:
        _save_playwright_debug_disk(config, page=page, result=result, stem=stem)
        return result

    try:
'''

    suffix = '''    except PlaywrightTimeoutError as exc:
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail=f"timeout:{exc}"[:200],
        )
        r = ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail=f"timeout:{exc}",
        )
        _save_playwright_debug_disk(
            config,
            page=page,
            result=r,
            stem="playwright_timeout",
        )
        return r
    except Exception as exc:
        d = str(exc)[:500]
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail=d[:200],
        )
        r = ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail=d,
        )
        _save_playwright_debug_disk(
            config,
            page=page,
            result=r,
            stem="playwright_exception",
        )
        return r


'''

    batch_fn = '''

@dataclass(frozen=True)
class VacancyApplySpec:
    """One vacancy in a UI apply batch (same browser session)."""

    autoparsed_vacancy_id: int
    hh_vacancy_id: str
    vacancy_url: str
    resume_hh_id: str
    cover_letter: str


def apply_to_vacancies_ui_batch(
    *,
    storage_state: dict[str, Any],
    items: list[VacancyApplySpec],
    config: HhUiApplyConfig,
    log_user_id: int | None = None,
    max_retries: int = 5,
    retry_initial_seconds: float = 10.0,
    retry_delay_cap_seconds: float = 600.0,
) -> list[tuple[int, ApplyResult]]:
    """One Chromium launch; sequential ``goto`` + apply per item; retries with backoff per item."""
    results: list[tuple[int, ApplyResult]] = []
    if not items:
        return results

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=config.headless,
                args=list(CHROMIUM_LAUNCH_ARGS),
            )
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            for spec in items:
                if not spec.vacancy_url.startswith("https://"):
                    results.append(
                        (
                            spec.autoparsed_vacancy_id,
                            ApplyResult(outcome=ApplyOutcome.ERROR, detail="invalid_vacancy_url"),
                        )
                    )
                    continue
                last: ApplyResult | None = None
                for attempt in range(max_retries):
                    page.goto(
                        spec.vacancy_url,
                        wait_until="domcontentloaded",
                        timeout=config.navigation_timeout_ms,
                    )
                    _jitter(config)
                    last = _apply_vacancy_flow_on_page(
                        page,
                        vacancy_url=spec.vacancy_url,
                        resume_hh_id=spec.resume_hh_id,
                        config=config,
                        log_user_id=log_user_id,
                        cover_letter=spec.cover_letter,
                    )
                    if apply_outcome_is_terminal_no_retry(last.outcome):
                        break
                    if not apply_outcome_is_retryable(last.outcome):
                        break
                    if attempt < max_retries - 1:
                        delay = apply_retry_delay_seconds(
                            attempt, retry_initial_seconds, retry_delay_cap_seconds
                        )
                        logger.info(
                            "hh_ui_apply_batch_retry",
                            log_user_id=log_user_id,
                            vacancy_id=spec.autoparsed_vacancy_id,
                            attempt=attempt + 1,
                            outcome=last.outcome.value,
                            next_delay_s=delay,
                        )
                        time.sleep(delay)
                results.append((spec.autoparsed_vacancy_id, last or ApplyResult(outcome=ApplyOutcome.ERROR, detail="empty")))
        finally:
            dispose_sync_browser_context(context, browser)
    return results

'''

    new_apply = prefix + inner_body + suffix + batch_fn
    return text[:start] + new_apply + text[end:]


def main() -> int:
    path = ROOT / "src" / "services" / "hh_ui" / "runner.py"
    text = path.read_text(encoding="utf-8")
    out = build_patched_runner(text)
    path.write_text(out, encoding="utf-8")
    print("patched", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
