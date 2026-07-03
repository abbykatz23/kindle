"""Load/save race results log."""
import json
import uuid
from config import Config


def load_race_results() -> list[dict]:
    if Config.RACE_RESULTS_FILE.exists():
        try:
            return json.loads(Config.RACE_RESULTS_FILE.read_text())
        except Exception:
            return []
    return []


def add_race_result(entry: dict) -> dict:
    results = load_race_results()
    entry = {**entry, "id": uuid.uuid4().hex[:8]}
    results.insert(0, entry)
    _save(results)
    return entry


def delete_race_result(result_id: str) -> bool:
    results = load_race_results()
    before = len(results)
    results = [r for r in results if r.get("id") != result_id]
    if len(results) < before:
        _save(results)
        return True
    return False


def race_results_context(max_entries: int = 5) -> str:
    """Format recent race results for inclusion in Claude prompts."""
    results = load_race_results()
    if not results:
        return "None"
    lines = []
    for r in results[:max_entries]:
        line = (
            f"  [{r.get('date', '?')}] {r.get('race_name', 'Race')} — "
            f"{r.get('distance_miles', '?')} mi in {r.get('finish_time', '?')} (max effort)"
        )
        if r.get("notes"):
            line += f" · {r['notes']}"
        lines.append(line)
    return "\n".join(lines)


def _save(results: list[dict]) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.RACE_RESULTS_FILE.write_text(json.dumps(results, indent=2))
