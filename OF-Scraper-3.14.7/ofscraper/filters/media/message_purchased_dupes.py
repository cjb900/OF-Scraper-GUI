"""Collapse Messages ↔ Purchased/Paid copies of the same media_id.

Import-safe (stdlib only) so unit tests can collect without CLI side effects.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable, List, Optional

_MSG_TYPES = frozenset({"messages", "message"})
_PAID_TYPES = frozenset({"paid", "purchased", "purchase"})


def media_response_bucket(responsetype: Optional[str]) -> str:
    """Map a response type string to messages / purchased / other."""
    rt = str(responsetype or "").strip().lower()
    if rt in _MSG_TYPES:
        return "messages"
    if rt in _PAID_TYPES:
        return "purchased"
    return "other"


def collapse_message_purchased_dupes(
    media: Iterable[Any],
    *,
    get_responsetype: Optional[Callable[[Any], Any]] = None,
) -> List[Any]:
    """Drop Purchased/Paid copies when the same media_id also exists in Messages.

    Prefer Messages. Other duplicates (reposts across posts/areas) are unchanged.
    """
    items = list(media or [])
    if not items:
        return items

    def _rt(ele: Any) -> str:
        if get_responsetype is not None:
            return media_response_bucket(get_responsetype(ele))
        try:
            return media_response_bucket(getattr(ele, "responsetype", None))
        except Exception:
            return "other"

    by_id: dict[Any, list] = defaultdict(list)
    for ele in items:
        mid = getattr(ele, "id", None)
        if mid is None:
            continue
        by_id[mid].append(ele)

    drop_ids: set[int] = set()
    for group in by_id.values():
        buckets = {_rt(ele) for ele in group}
        if "messages" not in buckets or "purchased" not in buckets:
            continue
        for ele in group:
            if _rt(ele) == "purchased":
                drop_ids.add(id(ele))

    if not drop_ids:
        return items
    return [ele for ele in items if id(ele) not in drop_ids]
