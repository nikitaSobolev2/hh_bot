"""Keyword filter expression matching.

Extracted from the original parser_script/hh_parser.py (lines 85-108).
Syntax: "|" = OR, "," = AND, "!" = NOT (prefix on a term after splitting on "|").

Examples:
  - ``frontend|backend`` — frontend OR backend (whole tokens).
  - ``senior,frontend`` — senior AND frontend.
  - ``react|backend,laravel!frontend`` — (react OR backend) AND laravel AND NOT frontend.
  - ``!vue`` — exclude vacancies mentioning ``vue`` as a whole token.

Within one ``|`` branch, ``!`` splits a clause: text before the first ``!`` is required
(positive), each segment after ``!`` is a forbidden token. Example: ``laravel!frontend``
requires ``laravel`` and forbids ``frontend``.

If the expression contains none of ``,``, ``|``, ``!``, runs of spaces are treated as AND
(e.g. ``python django`` → ``python,django``).

Each OR-term must appear as a whole token (Unicode \\w boundaries), not as a substring
inside a longer word.
"""

import re

_NON_ALPHA_RE = re.compile(r"[^a-zA-Zа-яА-ЯёЁ0-9\s]")
_MULTI_SPACE_RE = re.compile(r" +")
_WORD_BOUNDARY_PART_RE_TEMPLATE = r"(?<!\w){}(?!\w)"


def strip_symbols(text: str) -> str:
    """Replace punctuation with spaces so hyphen/slash compounds become separate tokens."""
    cleaned = _NON_ALPHA_RE.sub(" ", text)
    return _MULTI_SPACE_RE.sub(" ", cleaned).strip()


def _normalize_keyword_expr(expr: str) -> str:
    """Space-separated AND when no structural operators are present."""
    expr = expr.strip()
    if not expr:
        return ""
    if not any(c in expr for c in ",|!"):
        return ",".join(expr.split())
    return expr


def _part_matches_at_word_boundaries(haystack: str, part: str) -> bool:
    if not part:
        return False
    pattern = _WORD_BOUNDARY_PART_RE_TEMPLATE.format(re.escape(part))
    return re.search(pattern, haystack) is not None


def _or_branch_matches(haystack: str, branch: str) -> bool:
    """One alternative between ``|``; may contain ``!`` for negated tail tokens."""
    branch = branch.strip()
    if not branch:
        return False
    parts = branch.split("!")
    pos_raw = parts[0]
    neg_raw = parts[1:]
    for n in neg_raw:
        if not n.strip():
            continue
        term = strip_symbols(n.strip()).strip().lower()
        if not term:
            continue
        if _part_matches_at_word_boundaries(haystack, term):
            return False
    if not pos_raw.strip():
        return True
    pos = strip_symbols(pos_raw.strip()).strip().lower()
    if not pos:
        return True
    return _part_matches_at_word_boundaries(haystack, pos)


def matches_keyword_expression(haystack: str, keyword_expr: str) -> bool:
    if not keyword_expr or not keyword_expr.strip():
        return True

    expr = _normalize_keyword_expr(keyword_expr)
    if not expr:
        return True

    title_clean = strip_symbols(haystack).lower()

    for and_group in expr.split(","):
        and_group = and_group.strip()
        if not and_group:
            continue
        or_parts = [p.strip() for p in and_group.split("|") if p.strip()]
        if not or_parts:
            return False
        if not any(_or_branch_matches(title_clean, part) for part in or_parts):
            return False

    return True
