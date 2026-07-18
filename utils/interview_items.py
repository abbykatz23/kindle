"""CRUD for books/projects/wildcard items (interview prep time-tracking)."""
import json
import uuid
from datetime import date

from config import Config

ITEM_CATEGORIES = ("books", "projects", "wildcard")


def load_items() -> list[dict]:
    if Config.INTERVIEW_ITEMS_FILE.exists():
        try:
            return json.loads(Config.INTERVIEW_ITEMS_FILE.read_text())
        except Exception:
            return []
    return []


def save_items(items: list[dict]) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.INTERVIEW_ITEMS_FILE.write_text(json.dumps(items, indent=2))


def add_item(category: str, title: str) -> dict:
    if category not in ITEM_CATEGORIES:
        raise ValueError(f"Unknown category: {category!r}")
    title = title.strip()
    if not title:
        raise ValueError("title must not be empty")

    items = load_items()
    entry = {
        "id": uuid.uuid4().hex[:8],
        "category": category,
        "title": title,
        "status": "active",
        "created_at": date.today().isoformat(),
        "completed_at": None,
    }
    items.append(entry)
    save_items(items)
    return entry


def get_item(item_id: str) -> dict | None:
    for item in load_items():
        if item.get("id") == item_id:
            return item
    return None


def get_items(category: str | None = None, status: str | None = None) -> list[dict]:
    items = load_items()
    if category is not None:
        items = [i for i in items if i.get("category") == category]
    if status is not None:
        items = [i for i in items if i.get("status") == status]
    return items


def get_active_items(category: str) -> list[dict]:
    return get_items(category=category, status="active")


def mark_item_complete(item_id: str) -> bool:
    items = load_items()
    for item in items:
        if item.get("id") == item_id:
            item["status"] = "complete"
            item["completed_at"] = date.today().isoformat()
            save_items(items)
            return True
    return False
