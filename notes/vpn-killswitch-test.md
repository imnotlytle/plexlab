# Verifying the qBittorrent VPN kill-switch

Never trust a VPN download setup until you've confirmed two things:

## 1. qBittorrent's traffic exits via PIA (not your real IP)

Compare the NAS's real public IP with qBittorrent's exit IP — they must DIFFER.

```bash
# Real WAN IP of the NAS:
curl -s https://ipinfo.io/ip

# IP that qBittorrent actually exits from (runs inside gluetun's namespace):
docker exec qbittorrent curl -s https://ipinfo.io/ip
```

PASS = the two are different and the second is a PIA server IP.

## 2. If the tunnel drops, qBittorrent loses ALL connectivity (the kill-switch)

```bash
# Stop the tunnel:
docker stop gluetun

# qBittorrent should now have NO internet. This should FAIL / time out:
docker exec qbittorrent curl -s --max-time 8 https://ipinfo.io/ip ; echo "exit=$?"

# Bring it back:
docker start gluetun
```

PASS = the middle command times out / returns nothing (exit code non-zero). That proves
qBittorrent cannot reach the internet without the VPN — no leak is possible.

## Notes
- gluetun's forwarded port (PIA) is at: `docker exec gluetun cat /tmp/gluetun/forwarded_port`
  Optional enhancement: auto-feed that port into qBittorrent's listening port.
- Check tunnel status/logs: `docker logs gluetun --tail 40`
