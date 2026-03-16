"""Unit tests for Telegram text utilities."""

from __future__ import annotations

from src.services.telegram.text_utils import split_text_by_break, split_text_for_telegram


def test_split_text_returns_single_chunk_when_under_limit():
    """When text is under max_len, returns single chunk."""
    text = "Short message"
    result = split_text_for_telegram(text, max_len=100)
    assert result == ["Short message"]


def test_split_text_returns_empty_list_for_empty():
    """Empty or whitespace-only text returns empty list."""
    assert split_text_for_telegram("") == []
    assert split_text_for_telegram("   \n   ") == []


def test_split_text_splits_at_paragraph_boundary():
    """Split at double newline when content exceeds limit."""
    para1 = "A" * 100
    para2 = "B" * 100
    text = f"{para1}\n\n{para2}" * 25  # 25 paragraphs, total ~5000 chars
    result = split_text_for_telegram(text, max_len=1000)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 1000
        assert "\n\n" not in chunk or chunk.count("\n\n") == 0 or len(chunk) <= 1000


def test_split_text_splits_at_line_boundary_when_paragraph_too_long():
    """When a paragraph exceeds max_len, split at single newline."""
    lines = ["Line " + str(i) for i in range(100)]
    text = "\n".join(lines)
    result = split_text_for_telegram(text, max_len=200)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 200


def test_split_text_hard_splits_when_line_exceeds_limit():
    """When a single line exceeds max_len, hard split."""
    long_line = "x" * 500
    result = split_text_for_telegram(long_line, max_len=200)
    assert len(result) >= 2
    for chunk in result:
        assert len(chunk) <= 200


def test_split_text_exactly_at_limit_returns_single_chunk():
    """Text exactly at max_len returns single chunk."""
    text = "a" * 400
    result = split_text_for_telegram(text, max_len=400)
    assert result == [text]


# ── split_text_by_break ──────────────────────────────────────────────────────


def test_split_text_by_break_returns_parts_between_markers():
    """Splits by [BREAK] and returns non-empty chunks."""
    text = "Part one[BREAK]Part two[BREAK]Part three"
    result = split_text_by_break(text, max_len=5000)
    assert result == ["Part one", "Part two", "Part three"]


def test_split_text_by_break_single_part_no_marker_returns_one_chunk():
    """When no [BREAK], returns single chunk if under limit."""
    text = "Single part without break"
    result = split_text_by_break(text, max_len=5000)
    assert result == [text]


def test_split_text_by_break_empty_returns_empty_list():
    """Empty or whitespace-only text returns empty list."""
    assert split_text_by_break("", max_len=100) == []
    assert split_text_by_break("   \n   ", max_len=100) == []


def test_split_text_by_break_sub_splits_oversized_chunk():
    """Chunk exceeding max_len is sub-split by split_text_for_telegram."""
    long_part = "A" * 500
    text = f"Short[BREAK]{long_part}[BREAK]End"
    result = split_text_by_break(text, max_len=200)
    assert "Short" in result[0]
    assert "End" in result[-1]
    for chunk in result:
        assert len(chunk) <= 200
