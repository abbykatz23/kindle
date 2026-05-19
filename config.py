import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


class Config:
    # Paths
    DATA_DIR = BASE_DIR / "data"
    PLAN_FILE = DATA_DIR / "plan.json"
    BIRTHDAYS_FILE = DATA_DIR / "birthdays.json"
    STATE_FILE = DATA_DIR / "state.json"
    OUTPUT_IMAGE_PATH = BASE_DIR / "output" / "dashboard.png"

    # Kindle SSH
    KINDLE_HOST: str = os.getenv("KINDLE_HOST", "192.168.0.53")
    KINDLE_USER: str = os.getenv("KINDLE_USER", "root")
    KINDLE_PASSWORD: str = os.getenv("KINDLE_PASSWORD", "")
    KINDLE_IMAGE_PATH: str = os.getenv("KINDLE_IMAGE_PATH", "/tmp/dashboard.png")

    # Strava
    STRAVA_CLIENT_ID: str = os.getenv("STRAVA_CLIENT_ID", "")
    STRAVA_CLIENT_SECRET: str = os.getenv("STRAVA_CLIENT_SECRET", "")
    STRAVA_REFRESH_TOKEN: str = os.getenv("STRAVA_REFRESH_TOKEN", "")

    # LeetCode
    LEETCODE_USERNAME: str = os.getenv("LEETCODE_USERNAME", "")

    # Claude
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Flask
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Dashboard canvas (Kindle Paperwhite 1 native portrait resolution)
    DASHBOARD_WIDTH: int = 758
    DASHBOARD_HEIGHT: int = 1024
