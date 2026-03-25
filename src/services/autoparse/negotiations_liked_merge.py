"""Merge negotiations-sync targets into vacancy feed session liked/disliked lists."""

from __future__ import annotations


def merge_liked_from_negotiations_sync(
    liked_ids: list,
    disliked_ids: list,
    autoparsed_ids: set[int],
) -> tuple[list[int], list[int]]:
    """Append *autoparsed_ids* to liked; remove them from disliked."""
    liked_list = list(liked_ids)
    liked_set = set(liked_list)
    new_disliked = [x for x in disliked_ids if x not in autoparsed_ids]
    for apid in sorted(autoparsed_ids):
        if apid not in liked_set:
            liked_list.append(apid)
            liked_set.add(apid)
    return liked_list, new_disliked
