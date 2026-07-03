"""Load/save the daily interview prep coaching summary."""
import json
from config import Config


def load_interview_summary() -> dict | None:
    if Config.INTERVIEW_SUMMARY_FILE.exists():
        try:
            return json.loads(Config.INTERVIEW_SUMMARY_FILE.read_text())
        except Exception:
            return None
    return None


def save_interview_summary(summary: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Config.INTERVIEW_SUMMARY_FILE.write_text(json.dumps(summary, indent=2))
