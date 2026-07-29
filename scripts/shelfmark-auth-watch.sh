#!/bin/sh
# Restart Shelfmark automatically when the Calibre-Web user database changes.
#
# WHY: Shelfmark uses AUTH_METHOD=cwa and holds the Calibre-Web auth DB state, so a new user
# (or a changed password) is invisible to it until the container restarts. Their docs say
# "Restart container after changing Calibre-Web passwords." Doing that by hand every time a
# friend is added is the thing this removes.
#
# Watches the mtime of app.db and restarts the container when it moves. Debounced so a burst
# of writes (Calibre-Web touches the DB on login, reading progress, etc.) causes at most one
# restart per QUIET_SECONDS window.

DB=/volume1/Config/calibre-web/app.db
STATE=/volume1/docker/_backups/.shelfmark-auth-watch.stamp
LOG=/volume1/docker/_backups/shelfmark-auth-watch.log
QUIET_SECONDS=90        # don't restart more often than this

[ -f "$DB" ] || exit 0

now_mtime=$(stat -c %Y "$DB" 2>/dev/null) || exit 0
last_mtime=$(cat "$STATE" 2>/dev/null || echo 0)

# first run: just record where we are, don't restart
if [ "$last_mtime" = "0" ]; then
  echo "$now_mtime" > "$STATE"
  exit 0
fi

[ "$now_mtime" = "$last_mtime" ] && exit 0

# debounce: only act once the DB has been quiet for a bit, so we don't restart mid-write
age=$(( $(date +%s) - now_mtime ))
if [ "$age" -lt 20 ]; then
  exit 0        # changed very recently; wait for the next tick
fi

# rate limit
last_restart=$(cat "${STATE}.restart" 2>/dev/null || echo 0)
if [ $(( $(date +%s) - last_restart )) -lt "$QUIET_SECONDS" ]; then
  exit 0
fi

if docker restart book-downloader >/dev/null 2>&1; then
  echo "$(date '+%F %T') app.db changed -> restarted book-downloader" >> "$LOG"
  date +%s > "${STATE}.restart"
  echo "$now_mtime" > "$STATE"
else
  echo "$(date '+%F %T') app.db changed but restart FAILED" >> "$LOG"
fi

# keep the log from growing forever
tail -n 500 "$LOG" > "${LOG}.tmp" 2>/dev/null && mv "${LOG}.tmp" "$LOG"
