# NAS Homelab — Plan

A project to clean up and secure a home media + downloads setup on a UGREEN NAS.

## Environment (as of 2026-07-27)

- **NAS:** UGREEN (UGOS Pro — Debian-based, built-in Docker, SSH available)
- **Docker management:** moving from the UGOS GUI → docker compose over SSH
- **Router:** consumer (no VLANs) → isolation done at the Docker/container level
- **qBittorrent host:** the NAS, behind a PIA VPN with a kill-switch
- **Access model:** SSH enabled; Claude drives docker compose with approval on each command
- **Working style:** all configs written & reviewed locally on the PC (git), then deployed to the NAS. Nothing touches live services without approval.

## Target architecture

```
gluetun (PIA tunnel)  ── only internet exit for the download side
   └── qBittorrent (network_mode: service:gluetun) — no leak possible if VPN drops

media network (separate):  Plex  +  Overseerr
```

## Roadmap

- [x] **Phase 0 — Access setup:** SSH enabled, key auth working, project created
- [x] **Phase 1 — Inventory:** done → see `notes/inventory.md`
- [x] **Phase 3 — VPN download stack — DONE 2026-07-27:** gluetun (PIA **OpenVPN**, Toronto,
      port forwarding on) + qBittorrent via `network_mode: service:gluetun`. Kill-switch
      verified (exit IP = PIA, and zero connectivity when tunnel dropped). Old leaky
      `QbittorrentAmazon` stopped + auto-restart disabled. Stack: `/volume1/docker/vpn-qbittorrent`
- [ ] **Phase 2 — Media stack:** adopt Plex + Overseerr (already installed) into clean compose
- [ ] **Phase 4 — Isolation & hardening:** move host-mode services to bridge nets, minimal ports
- [ ] **Phase 5 — Cleanup & maintenance:** remove dead pia-qbitt-git networks, backups, updates

Note: Overseerr is **already running** (`DefiantJazz`) — Phase 2 is adopt/verify, not install.

## Changes log

- 2026-07-27: Set qBittorrent WebUI password (user `admin`). Repointed Sonarr/Radarr/Prowlarr
  download clients from the old `192.168.68.53:8080` PC to the NAS client at `127.0.0.1:8080`
  (all three connection-tested OK). qBittorrent WebUI username = `admin`.

### Overseerr fix (2026-07-27)
- Overseerr (`DefiantJazz`) was running but its Plex scan failed every 5 min. Two causes:
  1. Plex reached via a `plex.direct` hostname → intermittent DNS (`EAI_AGAIN`). Fixed by
     setting `plex.ip=192.168.68.56`, `port=32400`, `useSsl=false` (same-box, direct IP).
  2. Stale Plex auth token → scan got "Permission denied". Overseerr's scanner reads the
     **admin user's** `plexToken` (db `user` id=1), not `settings.plex.authToken`. Copied the
     valid owner token from Plex `Preferences.xml` (`PlexOnlineToken`) into both. Scan now completes.
- Sonarr/Radarr (incl. intentional 4K duplicates for 4K vs non-4K users) all connection-test OK.
- Backups made: `settings.json.bak.*` and `db.sqlite3.bak.*` in the Overseerr config dir.
- Minor leftover: other Overseerr users' Plex tokens (id 2-7) are also stale (401) — only affects
  their per-user watchlist sync; they'll refresh on next Plex login. Not blocking.

## Decisions log

- 2026-07-27: Chose gluetun kill-switch pattern over router-level isolation (consumer router can't VLAN).
- 2026-07-27: qBittorrent on the NAS (not a separate Pi) — single place to manage; isolation via Docker networking.

## Open items / needs

- PIA credentials — user provides directly to config; Claude never handles them.
- NAS LAN IP + SSH username/port.
- Inventory of what's currently running (Phase 1).
