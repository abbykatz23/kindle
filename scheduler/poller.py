"""
Triggers a dashboard re-render + push to the Kindle.

Without args (cron flow): unconditional refresh — polls APIs, re-renders, pushes.
With --tap-x/--tap-y: routes a tap via the shared handler (kept around mostly for testing;
                     in normal operation, taps come in through the Flask /tap endpoint).
"""
import argparse

from utils.tap_handler import handle_tap, trigger_refresh


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tap-x", type=int, help="X coordinate of a tap")
    parser.add_argument("--tap-y", type=int, help="Y coordinate of a tap")
    args = parser.parse_args()

    if args.tap_x is not None and args.tap_y is not None:
        print(handle_tap(args.tap_x, args.tap_y))
    else:
        trigger_refresh()
        print("Cron refresh complete.")


if __name__ == "__main__":
    main()
