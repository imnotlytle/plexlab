#!/bin/sh
# auto-update-containers.sh — nightly unattended container updates, with guardrails.
# Cron: 04:45 daily (after the 04:15 config backup, so every update night has a fresh backup).
#
# TIERS (deliberate, see PLAN.md 2026-08-16):
#   SAFE    — updated every night, no conditions. Stateless-ish services where a bad update is
#             an inconvenience, not an outage: tautulli, maintainerr, books stack, bazarr, caddy,
#             homepage, uptime-kuma, vaultwarden, flaresolverr, diun, both cloudflared tunnels,
#             adguard, and the nginx plex-shim.
#   TIMING  — media stack (plex/sonarr/radarr/prowlarr/overseerr): updated ONLY when Plex has
#             zero active sessions, so an update never kills someone's stream. Skipped nights
#             are logged and retried the next night.
#   MANUAL  — never touched here. vpn-qbittorrent (kill-switch must be re-verified by hand after
#             any change), dispatcharr (pre-1.0, feeds live TV), readarr (pinned; upstream dead).
#             Diun still emails when these have updates — ask Claude to do them.
#
# Log: /volume1/docker/_backups/auto-update.log  (trimmed to last 2000 lines each run)

LOG=/volume1/docker/_backups/auto-update.log
[ -f "$LOG" ] && tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exec >> "$LOG" 2>&1

echo ""
echo "===== auto-update $(date '+%Y-%m-%d %H:%M:%S') ====="

update() {  # update <dir> [compose args...]  — pull + up, log only when something changed
    dir="/volume1/docker/$1"; shift
    [ -d "$dir" ] || { echo "SKIP missing dir: $dir"; return; }
    cd "$dir" || return
    before=$(docker compose "$@" images -q 2>/dev/null | sort)
    docker compose "$@" pull -q 2>/dev/null
    docker compose "$@" up -d --quiet-pull 2>&1 | grep -iE "recreat|error" 
    after=$(docker compose "$@" images -q 2>/dev/null | sort)
    if [ "$before" != "$after" ]; then
        echo "UPDATED: $dir $*"
    fi
}

# ---- SAFE tier ----
update tautulli
update maintainerr
update audiobookshelf
update calibre-web -f docker-compose.yml
update calibre-web -f book-downloader.yml
update bazarr
update caddy
update homepage
update uptime-kuma
update vaultwarden
update flaresolverr
update diun
update tunnel
update minecraft-cloudflare
update adguard

# the shim needs its own careful invocation: pull+up scoped to the one service
cd /volume1/docker/dispatcharr && docker compose pull -q dispatcharr-plex-shim 2>/dev/null \
    && docker compose up -d --no-deps dispatcharr-plex-shim >/dev/null 2>&1

# ---- TIMING tier: media stack, only when nobody is watching ----
PREFS="/volume1/Config/Plex/Library/Application Support/Plex Media Server/Preferences.xml"
TOK=$(grep -o 'PlexOnlineToken="[^"]*"' "$PREFS" | cut -d'"' -f2)
SESS=$(curl -s -m 20 "http://127.0.0.1:32400/status/sessions?X-Plex-Token=$TOK" \
        | grep -o 'size="[0-9]*"' | head -1 | grep -o '[0-9]*')
if [ -z "$SESS" ]; then
    echo "MEDIA: could not read Plex sessions — skipping media stack (fail-safe)"
elif [ "$SESS" -gt 0 ]; then
    echo "MEDIA: $SESS active session(s) — skipping media stack tonight"
else
    cd /volume1/docker/media || exit 0
    before=$(docker compose images -q plex sonarr radarr prowlarr overseerr 2>/dev/null | sort)
    docker compose pull -q plex sonarr radarr prowlarr overseerr 2>/dev/null
    docker compose up -d --no-deps plex sonarr radarr prowlarr overseerr >/dev/null 2>&1
    after=$(docker compose images -q plex sonarr radarr prowlarr overseerr 2>/dev/null | sort)
    [ "$before" != "$after" ] && echo "UPDATED: media stack (plex/arrs/overseerr)"
    # readarr deliberately absent: pinned to a retired tag, and 'up -d' would resurrect a
    # container that may have been intentionally stopped.
fi

# ---- hygiene + health ----
docker image prune -f >/dev/null 2>&1
DOWN=$(docker ps -a --filter status=exited --filter status=restarting \
        --format '{{.Names}} ({{.Status}})' | grep -vE "recyclarr" )
[ -n "$DOWN" ] && echo "WARNING not running: $DOWN"
echo "done $(date '+%H:%M:%S')"
