"""Keyword filter expression matching.

Extracted from the original parser_script/hh_parser.py (lines 85-108).
Syntax: "|" = OR, "," = AND.
Example: "frontend|backend,fullstack" -> (frontend OR backend) AND fullstack.
"""

import re

_NON_ALPHA_RE = re.compile(r"[^a-zA-Zа-яА-ЯёЁ0-9\s]")


def strip_symbols(text: str) -> str:
    return _NON_ALPHA_RE.sub("", text)


def matches_keyword_expression(title: str, keyword_expr: str) -> bool:
    if not keyword_expr:
        return True

    title_clean = strip_symbols(title).lower()

    for and_group in keyword_expr.split(","):
        or_parts = [
            strip_symbols(part).strip().lower() for part in and_group.split("|") if part.strip()
        ]
        if or_parts and not any(part in title_clean for part in or_parts):
            return False

    return True
