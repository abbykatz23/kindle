"""
Triggers a dashboard re-render + push to the Kindle.

Without args (cron flow): polls APIs, re-renders, pushes.
With --tap-x/--tap-y: any tap currently just triggers a refresh. (We may map taps to
                     specific task toggles later.)
"""
import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent


def _trigger_render_and_push() -> None:
    subprocess.run(
        [sys.executable, str(_PROJECT_ROOT / "main.py")],
        check=True,
        cwd=str(_PROJECT_ROOT),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tap-x", type=int, help="X coordinate of a Kindle tap (currently logged but unused)")
    parser.add_argument("--tap-y", type=int, help="Y coordinate of a Kindle tap (currently logged but unused)")
    args = parser.parse_args()

    if args.tap_x is not None and args.tap_y is not None:
        print(f"Tap ({args.tap_x},{args.tap_y}) → refresh")

    _trigger_render_and_push()


if __name__ == "__main__":
    main()
