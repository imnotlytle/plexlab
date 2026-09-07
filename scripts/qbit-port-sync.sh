#!/bin/sh
# Two jobs, both tied to qBittorrent's health. Runs as root every 5 min via /etc/cron.d/qbit-port-sync.
#
# 1. WATCHDOG (added 2026-09-07): restart qBittorrent if it is not running.
#    qBittorrent uses `network_mode: service:wireguard-pia`, so it lives inside the VPN
#    container's network namespace. When the VPN container restarts, that namespace is
#    replaced and qBittorrent dies with exit 255 — and Docker's restart policy cannot bring
#    it back, because the netns it wants no longer exists. It then stays down silently:
#    the VPN container still looks "healthy" and still publishes :8080, so nothing appears
#    broken from outside. This actually happened — qBittorrent was dead for 4 days, Sonarr/
#    Radarr could not reach a download client, and 4 days of episodes never downloaded.
#
# 2. PORT SYNC: keep qBittorrent's listening port matched to PIA's forwarded port, which can
#    change on VPN reconnect; a mismatch cripples incoming peers.

STACK=/volume1/docker/vpn-qbittorrent

STATE=$(docker inspect -f '{{.State.Status}}' qbittorrent 2>/dev/null)
if [ "$STATE" != "running" ]; then
    echo "$(date '+%F %T') qbittorrent is '$STATE' — restarting (VPN netns likely cycled)"
    cd "$STACK" && docker compose up -d qbittorrent >/dev/null 2>&1
    sleep 20
    NEW=$(docker inspect -f '{{.State.Status}}' qbittorrent 2>/dev/null)
    echo "$(date '+%F %T') qbittorrent now: $NEW"
    # Confirm the tunnel is actually carrying its traffic before letting it seed/leech.
    VPNIP=$(docker exec qbittorrent curl -s -m 20 https://ipinfo.io/ip 2>/dev/null)
    WANIP=$(curl -s -m 20 https://ipinfo.io/ip 2>/dev/null)
    if [ -n "$VPNIP" ] && [ "$VPNIP" = "$WANIP" ]; then
        echo "$(date '+%F %T') !! KILL-SWITCH FAIL: qbit exit IP == WAN IP ($WANIP) — stopping qbittorrent"
        docker stop qbittorrent >/dev/null 2>&1
        exit 1
    fi
    echo "$(date '+%F %T') kill-switch ok (qbit exits via $VPNIP, wan is $WANIP)"
    exit 0    # let it settle; the next run in 5 min syncs the port
fi

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
