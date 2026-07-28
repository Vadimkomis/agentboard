"""Integer ranking invariants shared by backlog and Sprint ordering."""

from __future__ import annotations

from collections.abc import Sequence

from agentboard.domain.errors import DuplicateIdentifiersError, IncompleteReorderError


def validate_exact_order(current_ids: Sequence[int], requested_ids: Sequence[int]) -> None:
    if len(requested_ids) != len(set(requested_ids)):
        raise DuplicateIdentifiersError
    if len(current_ids) != len(requested_ids) or set(current_ids) != set(requested_ids):
        raise IncompleteReorderError


def contiguous_ranks(ordered_ids: Sequence[int]) -> dict[int, int]:
    return {identifier: index for index, identifier in enumerate(ordered_ids, start=1)}
