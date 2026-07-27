# NAS Inventory — 2026-07-27

Host: UGREEN DXP2800 (`DXP2800-FF69`), UGOS Pro, kernel 6.12, Docker 26.1.0.
Storage: `/volume1` = 22T pool, 12T used (~53%).

## Running containers

| Container | Image | Network mode | Notes |
|---|---|---|---|
| `linuxserver_plex-1` | linuxserver/plex | **host** | Media server |
| `DefiantJazz` | linuxserver/overseerr | **host** | Overseerr — **already installed** |
| `linuxserver_sonarr-1` | linuxserver/sonarr | **host** | TV automation |
| `linuxserver_radarr-1` | linuxserver/radarr | **host** | Movie automation |
| `linuxserver_readarr-1` | linuxserver/readarr:0.4.11-nightly | **host** | Books (nightly tag) |
| `PatPlexProwlarrv2` | linuxserver/prowlarr | **host** | Indexer manager |
| `flaresolverr_flaresolverr-1` | flaresolverr/flaresolverr | **host** | Cloudflare solver for indexers |
| `MsCobel` | advplyr/audiobookshelf | bridge | Audiobooks/podcasts |
| `QbittorrentAmazon` | linuxserver/qbittorrent | **bridge — NO VPN** | ⚠️ leaking real IP (see below) |
| `cloudflared` | cloudflare/cloudflared | minecraft-cloudflare_default | Cloudflare tunnel (inbound path) |
| `firefox-app-1` | ugreen/firefox | bridge | UGOS GUI app |
| `portainer_agent` | portainer/agent:2.16.2 | bridge | Portainer agent (a Portainer manages this host) |

Not shown / native: Plex group (gid 1001) exists. Minecraft ATM9 server + cloudflare folders present under `/volume1/docker`.

## Security findings (priority order)

1. **qBittorrent leaks real IP (CRITICAL).** `QbittorrentAmazon` is on a plain `bridge`
   network with no VPN container in its path. Host ports published on `0.0.0.0` + `::`:
   `6881/tcp`, `6881/udp`, `8080/tcp` (WebUI). All torrent traffic exits via the NAS's
   normal WAN connection = real home IP exposed. → Fix in Phase 3 (gluetun + PIA kill-switch).
   - qBit config: `/volume1/Config/qbittorrent` → `/config`
   - qBit downloads: `/volume1/Media/temp` → `/downloads`
2. **Plaintext PIA credentials.** `/volume1/docker/pia-qbitt-git/docker-compose.yaml`
   (world-readable `-rwxrwxrwx`) contains PIA user + password in cleartext. → Rotate the
   PIA password; store future creds only in gitignored `.env`.
3. **No isolation.** 7 services share `host` network mode. → Move to dedicated bridge
   network(s) with only required ports (Phase 4).
4. **Cloudflare tunnel(s).** `cloudflared` = inbound path from the internet. → Review what
   it exposes (later hardening).

## Dead / leftover to clean up

- Abandoned `pia-qbitt-git` stack: container not running, but leftover networks remain:
  `pia-qbitt-git_custom_network` (bridge), `pia-qbitt-git_default` (bridge),
  `pia-qbitt-git_external_network` (macvlan on eth0). Old approach used `j4ym0/pia-qbittorrent`
  (OpenVPN) with a macvlan assigning the container the host's own IP — broken/hacky. Replace,
  don't revive.
- Empty `config/ downloads/ openvpn/` dirs under `pia-qbitt-git`.

## Container naming

Mixed conventions: some compose-style (`linuxserver_sonarr-1`), some random/auto
(`DefiantJazz`, `MsCobel`, `QbittorrentAmazon`, `PatPlexProwlarrv2`). Standardize during cleanup.
