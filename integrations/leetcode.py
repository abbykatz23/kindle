from datetime import date

import requests

_GRAPHQL_URL = "https://leetcode.com/graphql"

_RECENT_SUBMISSIONS_QUERY = """
query recentSubmissions($username: String!, $limit: Int!) {
    recentAcSubmissionList(username: $username, limit: $limit) {
        id
        title
        titleSlug
        timestamp
    }
}
"""


def get_recent_accepted_submissions(username: str, limit: int = 10) -> list[dict]:
    resp = requests.post(
        _GRAPHQL_URL,
        json={
            "query": _RECENT_SUBMISSIONS_QUERY,
            "variables": {"username": username, "limit": limit},
        },
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"]["recentAcSubmissionList"]


def get_todays_submission(username: str) -> dict | None:
    """Return the most recent accepted submission from today, or None."""
    today = date.today().isoformat()
    for sub in get_recent_accepted_submissions(username):
        if date.fromtimestamp(int(sub["timestamp"])).isoformat() == today:
            return sub
    return None


def is_problem_completed_today(username: str) -> bool:
    if not username:
        return False
    return get_todays_submission(username) is not None
