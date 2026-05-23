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


def get_recent_accepted_submissions(username: str, limit: int = 50) -> list[dict]:
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


def get_todays_submission(username: str, slug: str | None = None) -> dict | None:
    """
    Return today's accepted submission, optionally filtered to a specific problem.

    If slug is given, returns the accepted submission for that exact problem from today.
    If slug is None, returns the most recent accepted submission from today.
    """
    today = date.today().isoformat()
    for sub in get_recent_accepted_submissions(username):
        submitted_on = date.fromtimestamp(int(sub["timestamp"])).isoformat()
        if submitted_on != today:
            continue
        if slug is not None and sub["titleSlug"] != slug:
            continue
        return sub
    return None


def is_problem_completed_today(username: str, slug: str | None = None) -> bool:
    """Return True iff (the specific problem `slug`, or any problem) was accepted today."""
    if not username:
        return False
    return get_todays_submission(username, slug) is not None
