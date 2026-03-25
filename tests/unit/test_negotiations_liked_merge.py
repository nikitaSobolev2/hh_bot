"""Tests for negotiations liked merge (no heavy imports)."""

from src.services.autoparse.negotiations_liked_merge import merge_liked_from_negotiations_sync


def test_merge_liked_appends_and_removes_dislike():
    liked, disliked = merge_liked_from_negotiations_sync([1], [10, 20], {20, 30})
    assert 20 in liked and 30 in liked
    assert 10 in disliked
    assert 20 not in disliked


def test_merge_liked_idempotent():
    liked, disliked = merge_liked_from_negotiations_sync([1, 2], [], {2})
    assert liked == [1, 2]
