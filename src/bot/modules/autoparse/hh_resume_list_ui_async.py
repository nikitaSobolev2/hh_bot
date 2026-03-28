"""Async wrapper for threaded HH UI resume list (shared by feed and autorespond)."""

from __future__ import annotations

import asyncio

# Playwright resume list can be slow; show loading UI and cap wait so the user is not stuck silent.
LIST_RESUMES_TIMEOUT_S = 120.0


async def run_list_resumes_ui_async(
    storage_state: dict,
    user_id: int,
):
    from src.services.hh_ui.config import HhUiApplyConfig
    from src.services.hh_ui.runner import list_resumes_ui

    cfg = HhUiApplyConfig.from_settings()
    return await asyncio.wait_for(
        asyncio.to_thread(
            list_resumes_ui,
            storage_state=storage_state,
            config=cfg,
            log_user_id=user_id,
        ),
        timeout=LIST_RESUMES_TIMEOUT_S,
    )
