#!/bin/sh
# Runs as a daemon on the Kindle.
# Listens for screen tap events via lipc and SSHs back to the Pi to trigger a poll.
#
# Prerequisites on Kindle: dropbear SSH client, lipc
# Usage: sh /mnt/us/kindle/tap_listener.sh &

PI_HOST="<PI_IP>"
PI_USER="<PI_USER>"
PI_PROJECT_DIR="/home/<PI_USER>/kindle-dashboard"
DEBOUNCE_SECONDS=10

while true; do
    lipc-wait-event -s com.lab126.powerd userActivityEvent 2>/dev/null

    sleep "$DEBOUNCE_SECONDS"

    ssh -o StrictHostKeyChecking=no \
        -o ConnectTimeout=5 \
        "${PI_USER}@${PI_HOST}" \
        "cd ${PI_PROJECT_DIR} && python scheduler/poller.py" \
        2>/dev/null &
done
