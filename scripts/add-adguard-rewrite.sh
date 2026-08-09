#!/bin/sh
# Add a DNS rewrite to AdGuard Home (split-horizon: a real public hostname pointed at the LAN IP).
#
# Usage:  add-adguard-rewrite.sh <domain> <ip>
# e.g.    add-adguard-rewrite.sh vault.patplex.net 192.168.68.56
#
# WHY A SCRIPT AND NOT A ONE-LINER: AdGuardHome.yaml is root-owned, and PLAN.md records that
# editing AdGuard rules through nested ssh -> docker heredocs mangles the content. Write the edit
# to a file, mount it, run it there.
#
# WHY STOP THE CONTAINER FIRST: AdGuard rewrites its whole config file on shutdown. Editing the
# YAML while it is running means the edit is silently overwritten when it next writes out.
# This costs a few seconds of LAN-wide DNS downtime — clients retry, but do not run it casually.
#
# Idempotent: exits early if the domain is already present.
set -e

DOMAIN="$1"
IP="$2"
[ -n "$DOMAIN" ] && [ -n "$IP" ] || { echo "usage: $0 <domain> <ip>" >&2; exit 2; }

CONF=/opt/adguardhome/conf/AdGuardHome.yaml
HOSTCONF=/volume1/docker/adguardhome/conf/AdGuardHome.yaml

if docker exec adguardhome grep -q "domain: $DOMAIN\$" "$CONF" 2>/dev/null; then
    echo "already present: $DOMAIN"
    exit 0
fi

echo "backing up..."
docker exec adguardhome cp "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"

echo "stopping adguardhome (brief DNS outage)..."
docker stop adguardhome >/dev/null

# Insert the new entry immediately after the `  rewrites:` key, preserving indentation.
docker run --rm -v /volume1/docker/adguardhome/conf:/conf alpine sh -c "
awk -v d='$DOMAIN' -v ip='$IP' '
  /^  rewrites:/ && !done {
      print
      print \"    - domain: \" d
      print \"      answer: \" ip
      print \"      enabled: true\"
      done=1
      next
  }
  { print }
' /conf/AdGuardHome.yaml > /conf/AdGuardHome.yaml.new && mv /conf/AdGuardHome.yaml.new /conf/AdGuardHome.yaml
"

echo "starting adguardhome..."
docker start adguardhome >/dev/null
sleep 8

echo "verifying..."
docker exec adguardhome grep -A2 "domain: $DOMAIN\$" "$CONF" || {
    echo "FAILED: entry not found after restart" >&2
    exit 1
}
echo "OK: $DOMAIN -> $IP"
