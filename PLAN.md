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

### Cloudflare tunnel audit + migration (2026-07-27)
- Domain: **patplex.net**. Two tunnels exist:
  - **Overseerr** (`d22066e0`) — public routes: `overseerr.patplex.net`→NAS:5055,
    `abs.patplex.net`→NAS:13378 (Audiobookshelf), catch-all 404. Connector WAS running on
    the `.53` PC (not the NAS) — a fragility since `.53` is being retired.
  - **atm-9** (`cb5836b2`) — Minecraft; NO public/CIDR routes; connector runs on the NAS.
- Security verdict: only Overseerr + Audiobookshelf are internet-exposed (both have their own
  logins, meant to be public). Sonarr/Radarr/Prowlarr/qBittorrent/Plex are NOT exposed. Good.
- **Migration done:** stood up `cloudflared-media` on the NAS (`/volume1/docker/tunnel`) as a
  2nd connector on the Overseerr tunnel (HA, zero downtime). Verified both public URLs return
  200 served via the NAS. → **`.53` can now be retired.**
- Cleanup: moved the dead-tunnel compose (`/volume1/docker/cloudflare`, referenced nonexistent
  tunnel `b7d636ff`) to `_disabled_cloudflare_deadtunnel_*`. Updated both cloudflared images to latest.
- Tunnel token stored only in gitignored `.env` on the NAS (chmod 600).
- Optional future hardening: put Cloudflare Access in front of the two hostnames — but note it can
  interfere with the Overseerr/Audiobookshelf mobile apps, so weigh that before enabling.

### Isolation pass (2026-07-27)
- Consumer router = no VLANs, so deep network isolation isn't available. Decided NOT to
  re-architect the working host-mode *arr/Plex stack into bridge networks (marginal security
  gain, real breakage risk). The high-value isolation (torrent stack behind VPN) was already done.
- **Removed FlareSolverr** — it was running unused (empty Prowlarr IndexerProxies table) and
  exposed an unauthenticated headless browser on the LAN (:8191). Container removed, 8191 closed.
  Re-add recipe saved at `docker/optional/flaresolverr.yml`.
- Noted but NOT changed (user opted out): Radarr auth = `DisabledForLocalAddresses` (open on LAN).
  Sonarr/Prowlarr/Readarr require login.
- Future real isolation lever = a VLAN-capable router (hardware upgrade).

### Housekeeping + import-pipeline fix (2026-07-27)
- Removed inert `QbittorrentAmazon` container and the 3 dead `pia-qbitt-git` networks.
- **Fixed broken imports** (Plex wasn't seeing new downloads). Root cause: qBittorrent mounted
  `/volume1/Media/temp:/downloads` but the *arr apps mount `/volume1/Media/temp/downloads:/downloads`
  — two different host folders, so Radarr looked where the file wasn't (and couldn't even see it).
  Fix: changed qBittorrent's mount to `/volume1/Media/temp/downloads:/downloads` to match the *arr
  apps; moved the stuck file into that folder; rechecked the torrent (still seeding); deleted the
  stale `.53`/UNC remote path mappings from Radarr + Sonarr. Verified: "The Debt Collector (2026)"
  imported to `/volume1/Media/Movies/...`, hasFile=true, and now shows in Plex. Applies to all
  future downloads.

### Config backups (2026-07-27)
- Script `scripts/backup-configs.sh` → deployed to `/volume1/docker/scripts/backup-configs.sh`.
  Snapshots `/volume1/Config` + `/volume1/docker` to `/volume1/docker/_backups/config/`
  (excludes re-downloadable caches + `#recycle`; keeps last 14). First run = ~1.5 GB.
- Scheduling: user's crontab spool is root-only, so scheduled via a root `/etc/cron.d` entry
  (one sudo command). Daily 04:15, logs to `/volume1/docker/_backups/backup.log`.
- Archive contains `.env` secrets (PIA, Cloudflare token) — fine locally; treat as sensitive if copied off-box.
- **LOCAL backup only** (same pool) — protects against config corruption / bad upgrades / deletes,
  NOT total pool loss. TODO for Pat: add an offsite/external copy of `/volume1/docker/_backups`.

## Decisions log

- 2026-07-27: Chose gluetun kill-switch pattern over router-level isolation (consumer router can't VLAN).
- 2026-07-27: qBittorrent on the NAS (not a separate Pi) — single place to manage; isolation via Docker networking.

## Open items / needs

- PIA credentials — user provides directly to config; Claude never handles them.
- NAS LAN IP + SSH username/port.
- Inventory of what's currently running (Phase 1).
