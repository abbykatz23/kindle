"""Render dashboard with mock data and save to output/dashboard.png — no Kindle push."""
from datetime import datetime

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    now = datetime.now()
    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    last_refreshed_label = f"{date_part} at {time_part}"

    img = render_dashboard(
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
