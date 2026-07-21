"""Composition/query layer for learning/project time-tracking.

This is the single source of truth for row order and identity, imported by both
the render pipeline (via main.py) and the tap handler, so rendering and
tap-hit-testing can never drift apart — mirrors the existing convention where
weekly-row layout constants live in one place and get imported everywhere needed.
"""
from datetime import date

from utils.learning_items import ITEM_CATEGORIES, get_active_items
from utils.time_log import FIXED_CATEGORIES, get_totals_for_date

CATEGORY_LABELS = {
    "system_design": "System Design",
    "books": "Books",
    "projects": "Projects",
    "wildcard": "Wildcard",
}

FIXED_LABELS = {
    "system_design": "System Design Learning",
}


def get_loggable_rows(on_date: date | None = None) -> list[dict]:
    """Ordered rows for the Kindle detail view / frontend log-time UI.

    Order: system_design, then active books, projects, wildcard
    (oldest-created first within each category).
    """
    on_date = on_date or date.today()
    totals = get_totals_for_date(on_date)
    rows: list[dict] = []

    for category in FIXED_CATEGORIES:
        rows.append({
            "category": category,
            "item_id": None,
            "label": FIXED_LABELS[category],
            "today_minutes": totals.get((category, None), 0),
        })

    for category in ITEM_CATEGORIES:
        items = sorted(get_active_items(category), key=lambda i: i.get("created_at", ""))
        for item in items:
            rows.append({
                "category": category,
                "item_id": item["id"],
                "label": item["title"],
                "today_minutes": totals.get((category, item["id"]), 0),
            })

    return rows
