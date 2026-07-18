"""Render dashboard with mock data and save to output/dashboard.png — no Kindle push."""
from datetime import datetime

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    now = datetime.now()
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    last_refreshed_label = f"{date_part} at {time_part}"

    interview_summary = {
        "system_design": {"today_minutes": 30},
        "behavioral": {"today_minutes": 0},
        "books": {"active_count": 2, "today_minutes": 45},
        "projects": {"active_count": 1, "today_minutes": 15},
        "wildcard": None,
    }
    leetcode_today = {"count": 2, "problems": [{"title": "Two Sum"}, {"title": "Three Sum"}]}

    img = render_dashboard(
        interview_summary=interview_summary,
        leetcode_today=leetcode_today,
        run={"type": "easy", "distance_miles": 5.0, "notes": "Recovery pace — keep HR under 140."},
        run_completed=False,
        birthdays=[
            {"name": "Chase", "date": "05-22", "days_until": 0, "formatted_date": "May 22nd"},
            {"name": "Caroline", "date": "05-25", "days_until": 3, "formatted_date": "May 25th"},
        ],
        last_refreshed_label=last_refreshed_label,
    )

    path = save_dashboard(img)
    print(f"Mock dashboard saved to {path}")


if __name__ == "__main__":
    main()
