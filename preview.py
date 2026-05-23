"""Render dashboard with mock data and save to output/dashboard.png — no Kindle push."""
from datetime import datetime

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    now = datetime.now()
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    last_refreshed_label = f"{date_part} at {time_part}"

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
            {"name": "Alice", "date": "05-22", "days_until": 0, "formatted_date": "May 22nd"},
            {"name": "Bob", "date": "05-24", "days_until": 2, "formatted_date": "May 24th"},
        ],
        last_refreshed_label=last_refreshed_label,
    )

    path = save_dashboard(img)
    print(f"Mock dashboard saved to {path}")


if __name__ == "__main__":
    main()
