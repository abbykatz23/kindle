#!/bin/sh
# Substitutes this machine's LAN IP into tap_listener.sh and deploys it to
# the Kindle over SCP. Run from the project root, on whatever host is
# currently running the Flask app (the Pi in production):
#
#   sh kindle/deploy_tap_listener.sh
#
# Requires DASHBOARD_HOST_IP (this machine's own LAN IP — the address the
# Kindle should POST tap coordinates to), KINDLE_HOST, and KINDLE_USER set
# in .env. Re-run this any time the host's IP changes (new hardware, DHCP
# lease change, etc.) instead of hand-editing tap_listener.sh.

set -eu
cd "$(dirname "$0")/.."

set -a
. ./.env
set +a

: "${DASHBOARD_HOST_IP:?Set DASHBOARD_HOST_IP in .env to this machine's LAN IP}"
: "${KINDLE_HOST:?Set KINDLE_HOST in .env}"
: "${KINDLE_USER:?Set KINDLE_USER in .env}"

TMP=$(mktemp)
sed "s/__DASHBOARD_HOST_IP__/$DASHBOARD_HOST_IP/" kindle/tap_listener.sh > "$TMP"

scp "$TMP" "$KINDLE_USER@$KINDLE_HOST:/mnt/us/kindle/tap_listener.sh"
rm "$TMP"

echo "Deployed tap_listener.sh with HOST=$DASHBOARD_HOST_IP"
echo "On the Kindle, (re)start it: sh /mnt/us/kindle/tap_listener.sh &"
