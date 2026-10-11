"""Redaction helpers for what public (non-owner) web visitors can see."""
import re


def mask_name(name: str) -> str:
    """'Chase Smith' -> 'XXXXX XXXXX' — hides the name but keeps the layout."""
    return re.sub(r"\S", "X", name)


def mask_birthdays(birthdays: list[dict]) -> list[dict]:
    return [{**b, "name": mask_name(b.get("name", ""))} for b in birthdays]
