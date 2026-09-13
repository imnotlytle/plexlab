#!/bin/sh
# Exempt the Nest thermostat from AdGuard filtering, keyed to its MAC (not IP — this LAN's
# DHCP reassigns addresses between devices, which already caused two misdiagnoses).
# Verifies DNS after and rolls back automatically if AdGuard won't come up.
set -e
CONF=/opt/adguardhome/conf/AdGuardHome.yaml
HOSTDIR=/volume1/docker/adguardhome/conf
STAMP=$(date +%Y%m%d-%H%M%S)

if docker exec adguardhome grep -q "3c:31:74:e7:a1:d6" "$CONF" 2>/dev/null; then
    echo "already present"; exit 0
fi

echo "backing up..."
docker exec adguardhome cp "$CONF" "$CONF.bak.$STAMP"
docker stop adguardhome >/dev/null

docker run --rm -v "$HOSTDIR":/conf alpine sh -c '
awk "
  /^  persistent: \[\]/ && !done {
      print \"  persistent:\"
      print \"    - name: nest-thermostat\"
      print \"      ids:\"
      print \"        - 3c:31:74:e7:a1:d6\"
      print \"      use_global_settings: false\"
      print \"      filtering_enabled: false\"
      print \"      parental_enabled: false\"
      print \"      safebrowsing_enabled: false\"
      print \"      safe_search:\"
      print \"        enabled: false\"
      print \"      use_global_blocked_services: false\"
      print \"      blocked_services:\"
      print \"        schedule:\"
      print \"          time_zone: Local\"
      print \"        ids: []\"
      print \"      upstreams: []\"
      print \"      tags: []\"
      print \"      ignore_querylog: false\"
      print \"      ignore_statistics: false\"
      done=1
      next
  }
  { print }
" /conf/AdGuardHome.yaml > /conf/AdGuardHome.yaml.new && mv /conf/AdGuardHome.yaml.new /conf/AdGuardHome.yaml
'

docker start adguardhome >/dev/null
sleep 12

# Verify DNS actually works; roll back if not.
if nslookup plex.home 192.168.68.56 >/dev/null 2>&1 && nslookup google.com 192.168.68.56 >/dev/null 2>&1; then
    echo "OK: adguard up, DNS resolving, nest exempted by MAC"
else
    echo "!! DNS FAILED — rolling back"
    docker stop adguardhome >/dev/null
    docker run --rm -v "$HOSTDIR":/conf alpine sh -c "cp /conf/AdGuardHome.yaml.bak.$STAMP /conf/AdGuardHome.yaml" 2>/dev/null || true
    docker start adguardhome >/dev/null
    sleep 10
    nslookup plex.home 192.168.68.56 >/dev/null 2>&1 && echo "rolled back, DNS restored" || echo "!! STILL BROKEN — manual check needed"
    exit 1
fi
