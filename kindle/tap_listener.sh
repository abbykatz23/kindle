#!/bin/sh
# Kindle tap listener — reads touch coordinates from evdev and SSHs them to the Pi.
#
# Prerequisites on Kindle: dropbear SSH client, getevent (busybox-extras), key auth to Pi
# Usage: sh /mnt/us/kindle/tap_listener.sh &
#
# Tunables (may need adjustment per firmware):
#   TOUCH_DEV  — touchscreen evdev path. Find with: getevent -p   (look for ABS_MT_POSITION_X)
#   PI_HOST / PI_USER — Pi address and user

PI_HOST="<PI_IP>"
PI_USER="<PI_USER>"
PI_PROJECT_DIR="/home/<PI_USER>/kindle-dashboard"
DEBOUNCE_SECONDS=2

# Auto-detect the touchscreen device, or override here:
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

echo "Listening on $TOUCH_DEV"

# Parse getevent output. Each line is:
#   /dev/input/eventN: TYPE CODE VALUE
# We want EV_ABS (0003) with ABS_MT_POSITION_X (0035) and ABS_MT_POSITION_Y (0036),
# then SYN_REPORT (0000 0000 00000000) signals end of a coalesced event.
# We send when the touch-up arrives (BTN_TOUCH=014a value 0, or tracking_id = -1).

X=""
Y=""
LAST_TAP=0

getevent -lt "$TOUCH_DEV" 2>/dev/null | while read -r LINE; do
    # Example line: [    1234.567890] EV_ABS       ABS_MT_POSITION_X    000001ee
    case "$LINE" in
        *ABS_MT_POSITION_X*|*ABS_X*)
            X=$(printf '%d' "0x$(echo "$LINE" | awk '{print $NF}')")
            ;;
        *ABS_MT_POSITION_Y*|*ABS_Y*)
            Y=$(printf '%d' "0x$(echo "$LINE" | awk '{print $NF}')")
            ;;
        *BTN_TOUCH*"00000000"*|*ABS_MT_TRACKING_ID*"ffffffff"*)
            # Touch released — fire if we have coords
            NOW=$(date +%s)
            if [ -n "$X" ] && [ -n "$Y" ] && [ $((NOW - LAST_TAP)) -ge $DEBOUNCE_SECONDS ]; then
                LAST_TAP=$NOW
                ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
                    "${PI_USER}@${PI_HOST}" \
                    "cd ${PI_PROJECT_DIR} && .venv/bin/python scheduler/poller.py --tap-x ${X} --tap-y ${Y}" \
                    >/dev/null 2>&1 &
            fi
            X=""; Y=""
            ;;
    esac
done
