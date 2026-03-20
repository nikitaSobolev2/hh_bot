"""Keyword filter expression matching.

Extracted from the original parser_script/hh_parser.py (lines 85-108).
Syntax: "|" = OR, "," = AND.
Example: "frontend|backend,fullstack" -> (frontend OR backend) AND fullstack.

Each OR-term must appear as a whole token (Unicode \\w boundaries), not as a
substring inside a longer word. Trade-off: e.g. ``vue`` does not match a single
token ``vuejs`` unless the text also contains ``vue`` as its own word; same for
``django`` vs ``djangorest`` — add explicit variants to the filter if needed.
"""

import re

_NON_ALPHA_RE = re.compile(r"[^a-zA-Zа-яА-ЯёЁ0-9\s]")
_MULTI_SPACE_RE = re.compile(r" +")
_WORD_BOUNDARY_PART_RE_TEMPLATE = r"(?<!\w){}(?!\w)"


def strip_symbols(text: str) -> str:
    """Replace punctuation with spaces so hyphen/slash compounds become separate tokens."""
    cleaned = _NON_ALPHA_RE.sub(" ", text)
    return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


def _part_matches_at_word_boundaries(haystack: str, part: str) -> bool:
    if not part:
        return False
    pattern = _WORD_BOUNDARY_PART_RE_TEMPLATE.format(re.escape(part))
    return re.search(pattern, haystack) is not None


def matches_keyword_expression(title: str, keyword_expr: str) -> bool:
    if not keyword_expr:
        return True

    title_clean = strip_symbols(title).lower()

    for and_group in keyword_expr.split(","):
        or_parts = [
            strip_symbols(part).strip().lower() for part in and_group.split("|") if part.strip()
        ]
        if or_parts and not any(
            _part_matches_at_word_boundaries(title_clean, part) for part in or_parts
        ):
            return False

    return True
