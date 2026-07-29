#!/bin/sh
# Keep qBittorrent's listening port matched to PIA's forwarded port.
# PIA's forwarded port can change on VPN reconnect; a mismatch cripples incoming peers.
# Reads the port from thrnz/docker-wireguard-pia's shared file (falls back to gluetun's).
# Run every few minutes via cron.

# Credentials come from a gitignored file on the NAS, so this script is safe in a public repo.
CREDS=${CREDS:-/volume1/docker/scripts/.creds}
[ -f "$CREDS" ] && . "$CREDS"
QBIT_USER=${QBIT_USER:-admin}
: "${QBIT_PASS:?QBIT_PASS not set — create $CREDS}"

PORT=$(cat /volume1/docker/wireguard-pia/shared/port.dat 2>/dev/null)
[ -z "$PORT" ] && PORT=$(docker exec gluetun cat /tmp/gluetun/forwarded_port 2>/dev/null)   # gluetun fallback
case "$PORT" in ''|*[!0-9]*) exit 0 ;; esac   # no valid port yet

cj=$(mktemp)
curl -s -c "$cj" "http://localhost:8080/api/v2/auth/login" \
     --data-urlencode "username=$QBIT_USER" --data-urlencode "password=$QBIT_PASS" -o /dev/null
CUR=$(curl -s -b "$cj" "http://localhost:8080/api/v2/app/preferences" \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('listen_port'))" 2>/dev/null)
if [ "$PORT" != "$CUR" ]; then
  curl -s -b "$cj" "http://localhost:8080/api/v2/app/setPreferences" \
       --data-urlencode "json={\"listen_port\":$PORT}" -o /dev/null
  echo "$(date '+%F %T') qbit listen_port $CUR -> $PORT"
fi
rm -f "$cj"
