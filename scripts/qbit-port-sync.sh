#!/bin/sh
# Keep qBittorrent's listening port matched to PIA's forwarded port (from gluetun).
# PIA's forwarded port can change on VPN reconnect; a mismatch cripples incoming peers.
# Run every few minutes via cron.

PORT=$(docker exec gluetun cat /tmp/gluetun/forwarded_port 2>/dev/null)
case "$PORT" in ''|*[!0-9]*) exit 0 ;; esac   # no valid port yet

cj=$(mktemp)
curl -s -c "$cj" "http://localhost:8080/api/v2/auth/login" --data "username=admin&password=admin123" -o /dev/null
CUR=$(curl -s -b "$cj" "http://localhost:8080/api/v2/app/preferences" \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('listen_port'))" 2>/dev/null)
if [ "$PORT" != "$CUR" ]; then
  curl -s -b "$cj" "http://localhost:8080/api/v2/app/setPreferences" \
       --data-urlencode "json={\"listen_port\":$PORT}" -o /dev/null
  echo "$(date '+%F %T') qbit listen_port $CUR -> $PORT"
fi
rm -f "$cj"
