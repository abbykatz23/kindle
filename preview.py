"""Render dashboard with mock data and save to output/dashboard.png — no Kindle push.

Use this for fast iteration on the render layout. Just run `python preview.py` from
the project root and refresh output/dashboard.png in your image viewer.
"""
from datetime import date

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    today = date.today()
    today_label = f"{today.strftime('%A, %B')} {today.day}"

    img = render_dashboard(
        interview_task={
            "type": "leetcode",
            "task": "Two Sum",
            "leetcode_slug": "two-sum",
            "notes": "Focus on the hash map approach; aim for O(n) time and space.",
        },
        interview_completed=True,
        run={
            "type": "easy",
            "distance_miles": 5.0,
            "notes": "Recovery pace — keep heart rate under 140.",
        },
        run_completed=False,
        birthdays=[
            {"name": "Alice", "date": "05-04", "days_until": 0},
            {"name": "Bob", "date": "05-06", "days_until": 2},
        ],
        today_label=today_label,
    )

    path = save_dashboard(img)
    print(f"Mock dashboard saved to {path}")


if __name__ == "__main__":
    main()
