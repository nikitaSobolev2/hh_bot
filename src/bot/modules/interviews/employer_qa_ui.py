"""HTML text builders for employer Q&A Telegram screens."""

from __future__ import annotations

import html

from src.core.i18n import I18nContext

BTN_LABEL_MAX = 44


def truncate_question_for_button(text: str, max_len: int = BTN_LABEL_MAX) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def build_employer_qa_list_text(header_html: str, i18n: I18nContext, *, count: int) -> str:
    title = html.escape(i18n.get("iv-employer-qa-title"))
    if count == 0:
        return (
            f"{header_html}\n\n<b>{title}</b>\n\n{html.escape(i18n.get('iv-employer-qa-empty'))}"
        )
    hint = html.escape(i18n.get("iv-employer-qa-list-hint"))
    return f"{header_html}\n\n<b>{title}</b>\n\n{hint}"


def build_employer_qa_item_full_html(
    header_html: str,
    *,
    result_header: str,
    q_label: str,
    a_label: str,
    question_text: str,
    answer_text: str,
) -> str:
    rh = html.escape(result_header)
    ql = html.escape(q_label)
    al = html.escape(a_label)
    return (
        f"{header_html}\n\n"
        f"<b>{rh}</b>\n\n"
        f"<b>{ql}</b>\n{html.escape(question_text)}\n\n"
        f"<b>{al}</b>\n{html.escape(answer_text)}"
    )
