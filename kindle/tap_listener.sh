#!/bin/sh
# Kindle tap listener — reads touch events one at a time via dd+hexdump and
# POSTs coordinates to the Flask /tap endpoint on the dashboard host.
#
# Usage: sh /mnt/us/kindle/tap_listener.sh

HOST="192.168.0.26"
PORT="5000"
DEBOUNCE_SECONDS=2
TOUCH_DEV="/dev/input/event0"

LAST_TAP=0
X=""
Y=""

# Open device once and hold the fd open so the kernel buffers all events
# for us. Without this, events arriving between dd invocations are lost.
exec 3< "$TOUCH_DEV"

while true; do
    LINE=$(dd <&3 bs=16 count=1 2>/dev/null | hexdump | head -1)
    set -- $LINE
    TYPE=$6; CODE=$7; V1=$8; V2=$9

    case "$TYPE:$CODE" in
        "0003:0035") X=$(( 0x$V1 )) ;;
        "0003:0036") Y=$(( 0x$V1 )) ;;
        "0003:0039")
            if [ "$V1" = "ffff" ] && [ "$V2" = "ffff" ]; then
                if [ -n "$X" ] && [ -n "$Y" ]; then
                    NOW=$(date +%s)
                    DIFF=$(( NOW - LAST_TAP ))
                    if [ "$DIFF" -ge "$DEBOUNCE_SECONDS" ]; then
                        LAST_TAP=$NOW
                        wget -q -O /dev/null "http://$HOST:$PORT/tap?x=$X&y=$Y" 2>/dev/null
                    fi
                fi
                X=""
                Y=""
            fi
            ;;
    esac
done
