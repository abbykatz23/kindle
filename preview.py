"""Render dashboard with mock week data and save to output/dashboard.png — no Kindle push."""
from datetime import date, datetime, timedelta

from dashboard.render import render_dashboard, save_dashboard


def main() -> None:
    now = datetime.now()
    today = now.date()
    monday = today - timedelta(days=today.weekday())

    date_part = f"{now.strftime('%A, %B')} {now.day}"
    time_part = now.strftime("%I:%M %p").lstrip("0")
    last_refreshed_label = f"{date_part} at {time_part}"

    # Mock: each day has a couple of tasks
    week_tasks: dict[str, list[dict]] = {}
    sample_lc = ["Two Sum", "Three Sum", "Reverse LL", "Valid Anagram",
                 "Binary Search", "Group Anagrams", "Top K Elements"]
    sample_lc_slugs = ["two-sum", "3sum", "reverse-linked-list", "valid-anagram",
                       "binary-search", "group-anagrams", "top-k-frequent-elements"]
    sample_other = ["DDIA Ch 1", "STAR prep", "DDIA Ch 2", "Mock interview",
                    "DDIA Ch 3", "Behavioral prep", "Review week"]

    for i in range(7):
        d = monday + timedelta(days=i)
        # Past days appear completed; today and future are pending
        is_done = d < today
        tasks = [
            {"type": "leetcode", "task": sample_lc[i], "leetcode_slug": sample_lc_slugs[i],
             "completed": is_done},
            {"type": "reading" if i % 2 == 0 else "behavioral", "task": sample_other[i],
             "completed": is_done},
        ]
        week_tasks[d.isoformat()] = tasks

    img = render_dashboard(
        week_tasks=week_tasks,
        today=today,
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
