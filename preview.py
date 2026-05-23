"""Render dashboard with mock data and save to output/dashboard.png — no Kindle push."""
from datetime import date

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    today = date.today()
    today_label = f"{today.strftime('%A, %B')} {today.day}"

    interview_tasks = [
        {"type": "leetcode", "task": "Two Sum", "leetcode_slug": "two-sum", "completed": True},
        {"type": "leetcode", "task": "Three Sum", "leetcode_slug": "three-sum", "completed": False},
        {"type": "reading", "task": "DDIA Chapter 3", "completed": True},
        {"type": "behavioral", "task": "STAR practice", "completed": False},
    ]

    img = render_dashboard(
        interview_tasks=interview_tasks,
        run={"type": "easy", "distance_miles": 5.0, "notes": "Recovery pace — keep HR under 140."},
        run_completed=False,
        birthdays=[
            {"name": "Alice", "date": "05-22", "days_until": 0},
            {"name": "Bob", "date": "05-24", "days_until": 2},
        ],
        today_label=today_label,
    )

    path = save_dashboard(img)
    print(f"Mock dashboard saved to {path}")


if __name__ == "__main__":
    main()
