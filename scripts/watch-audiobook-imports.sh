#!/bin/sh
# Watch qBittorrent until every torrent has finished, reporting whether each completed
# audiobook actually landed in the Audiobookshelf library.
#
# Shelfmark auto-imports torrents it is actively tracking, but a download that completes
# outside that window is left in /downloads. This makes that visible instead of silent.
#
# Read-only: reports, never moves or deletes anything.

QB=http://localhost:8080
LIB=/volume1/Media/Audio/merged
LOG=/volume1/docker/_backups/audiobook-import-watch.log
INTERVAL=${INTERVAL:-120}
MAX_MIN=${MAX_MIN:-720}          # give up after 12h

cj=$(mktemp)
login() { curl -s -c "$cj" "$QB/api/v2/auth/login" --data "username=admin&password=admin123" -o /dev/null; }
login

say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
say "=== watch started (poll every ${INTERVAL}s) ==="

deadline=$(( $(date +%s) + MAX_MIN*60 ))

while [ "$(date +%s)" -lt "$deadline" ]; do
  json=$(curl -s -b "$cj" "$QB/api/v2/torrents/info")
  case "$json" in
    \[*) : ;;
    *) login; sleep 5; continue ;;      # session expired
  esac

  report=$(printf '%s' "$json" | LIB="$LIB" python3 -c "
import sys, json, os, unicodedata
lib = os.environ['LIB']
ts = json.load(sys.stdin)
have = set()
for a in os.listdir(lib):
    p = os.path.join(lib, a)
    if os.path.isdir(p):
        for b in os.listdir(p):
            have.add(unicodedata.normalize('NFKD', b).lower())

def in_lib(name):
    n = unicodedata.normalize('NFKD', name).lower()
    return any(n[:14] in h or h[:14] in n for h in have)

pending = [t for t in ts if t['progress'] < 1.0]
done    = [t for t in ts if t['progress'] >= 1.0]
missing = [t for t in done if not in_lib(t['name'])]

for t in sorted(ts, key=lambda x: x['progress']):
    mark = 'done' if t['progress'] >= 1.0 else '%4.1f%%' % (t['progress']*100)
    flag = ''
    if t['progress'] >= 1.0:
        flag = ' [IN LIBRARY]' if in_lib(t['name']) else ' [NOT IMPORTED]'
    print('   %-32s %-8s %s%s' % (t['name'][:32], t['state'], mark, flag))
print('SUMMARY pending=%d done=%d not_imported=%d' % (len(pending), len(done), len(missing)))
if missing:
    print('NEEDS_IMPORT ' + ' | '.join(t['name'] for t in missing))
" 2>/dev/null)

  say "$report"

  case "$report" in
    *"pending=0"*) say "=== ALL TORRENTS COMPLETE ==="; break ;;
  esac
  sleep "$INTERVAL"
done

rm -f "$cj"
