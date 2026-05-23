#!/bin/sh
# Kindle tap listener — reads touch coordinates from evdev and POSTs them to the
# Flask app's /tap endpoint on the dashboard host.
#
# Prerequisites on Kindle:
#   - wget (busybox)
#   - getevent (busybox-extras)
# Usage:
#   sh /mnt/us/kindle/tap_listener.sh &
#
# Set these to the host running the Flask app (`python run.py` on the dashboard machine):
HOST="<DASHBOARD_HOST_IP>"
PORT="5000"
DEBOUNCE_SECONDS=2

# Auto-detect the touchscreen device (works on most Kindle firmwares).
# Override with TOUCH_DEV=/dev/input/eventN if needed.
TOUCH_DEV=""
for dev in /dev/input/event*; do
    if getevent -p "$dev" 2>/dev/null | grep -q "ABS_MT_POSITION_X"; then
        TOUCH_DEV="$dev"
        break
    fi
done

if [ -z "$TOUCH_DEV" ]; then
    echo "Could not find touchscreen device" >&2
    exit 1
fi

echo "Listening on $TOUCH_DEV -> http://${HOST}:${PORT}/tap"

X=""
Y=""
LAST_TAP=0

getevent -lt "$TOUCH_DEV" 2>/dev/null | while read -r LINE; do
    case "$LINE" in
        *ABS_MT_POSITION_X*|*ABS_X*)
            X=$(printf '%d' "0x$(echo "$LINE" | awk '{print $NF}')")
            ;;
        *ABS_MT_POSITION_Y*|*ABS_Y*)
            Y=$(printf '%d' "0x$(echo "$LINE" | awk '{print $NF}')")
            ;;
        *BTN_TOUCH*"00000000"*|*ABS_MT_TRACKING_ID*"ffffffff"*)
            NOW=$(date +%s)
            if [ -n "$X" ] && [ -n "$Y" ] && [ $((NOW - LAST_TAP)) -ge $DEBOUNCE_SECONDS ]; then
                LAST_TAP=$NOW
                wget -q --timeout=60 -O /dev/null \
                    "http://${HOST}:${PORT}/tap?x=${X}&y=${Y}" \
                    2>/dev/null
            fi
            X=""; Y=""
            ;;
    esac
done
