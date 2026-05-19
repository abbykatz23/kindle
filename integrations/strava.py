from datetime import date, datetime

import requests

from config import Config


def _get_access_token() -> str:
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": Config.STRAVA_CLIENT_ID,
            "client_secret": Config.STRAVA_CLIENT_SECRET,
            "refresh_token": Config.STRAVA_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_todays_run() -> dict | None:
    """Return the first Run activity logged today, or None if not found or not configured."""
    if not all([Config.STRAVA_CLIENT_ID, Config.STRAVA_CLIENT_SECRET, Config.STRAVA_REFRESH_TOKEN]):
        return None
    token = _get_access_token()
    today = date.today()
    after = int(datetime(today.year, today.month, today.day).timestamp())

    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"after": after, "per_page": 10},
    )
    resp.raise_for_status()

    for activity in resp.json():
        if activity["type"] == "Run":
            return {
                "id": str(activity["id"]),
                "name": activity["name"],
                "distance_miles": round(activity["distance"] / 1609.344, 2),
                "moving_time_seconds": activity["moving_time"],
                "date": today.isoformat(),
            }
    return None


def is_run_completed_today() -> bool:
    return get_todays_run() is not None
