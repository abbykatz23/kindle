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


_PROBLEM_LOOKUP_QUERY = """
query problemLookup($skip: Int!) {
    problemsetQuestionListV2(
        categorySlug: "algorithms"
        limit: 1
        skip: $skip
    ) {
        questions {
            questionFrontendId
            title
            titleSlug
        }
    }
}
"""


def get_problem_by_number(number: int) -> dict | None:
    """Return {questionFrontendId, title, titleSlug} for the given problem number, or None."""
    resp = requests.post(
        _GRAPHQL_URL,
        json={
            "query": _PROBLEM_LOOKUP_QUERY,
            "variables": {"skip": number - 1},
        },
        headers={
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com/problemset/",
        },
        timeout=10,
    )
    resp.raise_for_status()
    questions = resp.json()["data"]["problemsetQuestionListV2"]["questions"]
    if questions and questions[0]["questionFrontendId"] == str(number):
        return questions[0]
    return None


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
