#!/bin/sh
# Add a custom filtering rule to AdGuard Home's user_rules list.
#
# Usage: add-adguard-rule.sh '<rule>'
#   e.g. add-adguard-rule.sh '@@||us.nextlgsdp.com^$client=192.168.68.63'
#
# Same constraints as add-adguard-rewrite.sh, and solved the same way:
#  - AdGuardHome.yaml is root-owned, and the admin user cannot write it -> do the edit inside a
#    throwaway root container with the conf dir mounted.
#  - AdGuard REWRITES its whole config on shutdown, so an edit made while it runs is silently
#    discarded -> stop the container first. Costs a few seconds of LAN-wide DNS downtime.
#  - Nested ssh -> docker heredocs mangle content (see PLAN.md) -> keep the awk simple.
#
# Idempotent: exits early if the rule is already present.
set -e

RULE="$1"
[ -n "$RULE" ] || { echo "usage: $0 '<rule>'" >&2; exit 2; }

CONF=/opt/adguardhome/conf/AdGuardHome.yaml

if docker exec adguardhome grep -qF -- "$RULE" "$CONF" 2>/dev/null; then
    echo "already present: $RULE"
    exit 0
fi

echo "backing up..."
docker exec adguardhome cp "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"

echo "stopping adguardhome (brief DNS outage)..."
docker stop adguardhome >/dev/null

# Insert as the first entry under `user_rules:`. Written as a single-quoted YAML scalar because
# rules contain $ and | which must not be re-interpreted.
docker run --rm -v /volume1/docker/adguardhome/conf:/conf -e RULE="$RULE" alpine sh -c '
awk -v rule="$RULE" "
  /^user_rules:/ && !done { print; printf \"  - %c%s%c\n\", 39, rule, 39; done=1; next }
  { print }
" /conf/AdGuardHome.yaml > /conf/AdGuardHome.yaml.new && mv /conf/AdGuardHome.yaml.new /conf/AdGuardHome.yaml
'

echo "starting adguardhome..."
docker start adguardhome >/dev/null
sleep 8

echo "verifying..."
docker exec adguardhome grep -F -- "$RULE" "$CONF" >/dev/null || {
    echo "FAILED: rule not found after restart" >&2
    exit 1
}
echo "OK: $RULE"
