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

### AdGuard Home — network-wide DNS ad-blocking (2026-07-27)
- Can't run on the TP-Link Deco (locked firmware). Deployed on the NAS instead:
  `docker/adguard/docker-compose.yml` → `/volume1/docker/adguard`. DNS published on the LAN
  IP only (`192.168.68.56:53`) to avoid the 127.0.0.1:53 stub; admin UI on `:3000`.
- Deco: set the **DHCP Server** DNS to `192.168.68.56` (per-client, so AdGuard sees each device).
- Fixed post-cutover flakiness: default upstream was Quad9-DoH ONLY and was failing
  (`unexpected EOF`). Changed upstreams to Cloudflare + Google DoH, added 1.1.1.1/8.8.8.8
  fallback, set `ratelimit: 0`. Verified: 5 client devices querying, ~31% of queries blocked.
- TODO for Pat: reserve the NAS IP (`192.168.68.56`) in the Deco app so DNS never breaks; optionally
  add stronger blocklists (default misses e.g. googleadservices).

### Download optimization (2026-07-27)
- **qBittorrent speed:** listen_port was 6881 but PIA forwards 32309 → no incoming peers. Set to
  match; `scripts/qbit-port-sync.sh` (cron every 5 min) keeps qBit's port synced to gluetun's
  forwarded port across VPN reconnects. Rate limits already unlimited.
- **Auto-clean temp:** enabled Completed Download Handling + Remove Completed in Radarr & Sonarr.
  IMPORTANT: this only cleans up once qBittorrent finishes SEEDING — so a seed limit is required
  or torrents seed forever and nothing is removed. Set qBittorrent seed limit to ratio 1.0 OR
  3 days (4320 min), action=pause (`max_ratio_act=0`); *arr then removes torrent + temp files.
  Readarr API rejected the remove-completed call — TODO if needed.
- **1080p tier (Overseerr standard requests, profile id 4):** was preferring ~11 GB files
  (preferred 95 MB/min) + Remux allowed. Retuned quality definitions to prefer small/good
  (1080p ~22 MB/min pref, ~45 max; 720p ~12/25); removed Remux-1080p from Radarr profile.
  Kept x264 (NOT HEVC) — device audit showed heavy browser use (Chrome/Edge/Firefox can't
  play HEVC → would force transcode on a shared 8-user server).
- **4K tier (profile id 5):** Pat watches on an LG C5 (DV/Atmos capable). Created custom formats
  Dolby Vision (+1500), HDR10Plus (+300), Atmos (+200); demoted YTS 2160p (−200). 2160p sizes
  uncapped (DV files are big). Falls back to non-DV if unavailable.
- **KNOWN LIMITATION:** single Radarr + single `/Movies` Plex library for both tiers. A movie is
  either 1080p OR 4K (not both), and 4K DV is visible to all users → browser users would transcode
  it hard. Proper fix = separate Radarr4K instance + separate `/Movies4K` Plex library shared only
  with 4K-capable users. Offered as a follow-up.

### Tautulli (2026-07-27)
- Plex monitoring/stats at `http://192.168.68.56:8181` (`docker/tautulli`, config `/volume1/Config/Tautulli`).
- Pre-connected to Plex by seeding config.ini — NOTE: PMS keys (pms_ip/pms_token/pms_identifier/…)
  live under the **`[PMS]`** section, NOT `[General]` (first_run_complete goes under `[General]`).
  Used the owner PlexOnlineToken + machineIdentifier 8f83ec44…
- Wizard skipped, so no Tautulli web login is set — open on the LAN (fine like the *arr apps;
  add one in Settings > Web Interface if desired). Read-only against Plex; safe.

### VPN speed fix — switched PIA to WireGuard (2026-07-27)
- Symptom: downloads slow. Root cause chain (diagnosed the hard way): NAS internet is fine
  (954 Mbps direct); the bottleneck was **PIA-over-OpenVPN on the N100** (~14 Mbps ceiling,
  55% CPU on OpenVPN crypto). gluetun can ONLY do PIA via OpenVPN.
- Fix: run PIA over **WireGuard** via `thrnz/docker-wireguard-pia` (kernel WG). Benchmarked on
  the SAME well-seeded Ubuntu torrent: **OpenVPN 14 Mbps vs WireGuard 127 Mbps (~9x)**, VPN CPU
  ~0.5%. qBittorrent CPU (hashing/disk) becomes the limiter ~127 Mbps — near the NAS ceiling,
  matches Pat's old PC speed. Kill-switch + port forwarding verified. No need to switch providers.
- Config: `docker/download/docker-compose.yml` (wireguard-pia + qbittorrent), LOC=ca_toronto.
  Port-sync script reads `/volume1/docker/wireguard-pia/shared/port.dat` (gluetun fallback kept).
- LESSON: measure VPN speed with a WELL-SEEDED torrent (force-started past the queue) + compare
  direct-vs-tunnel. Single-stream HTTP tests and dead torrents gave misleading numbers for hours.
- Also fixed along the way: `max_active_downloads` had been lowered to 5 (stranded good torrents
  behind dead ones) → raised to 15/25.

## Decisions log

- 2026-07-27: Chose gluetun kill-switch pattern over router-level isolation (consumer router can't VLAN).
- 2026-07-27: qBittorrent on the NAS (not a separate Pi) — single place to manage; isolation via Docker networking.

## Open items / needs

- PIA credentials — user provides directly to config; Claude never handles them.
- NAS LAN IP + SSH username/port.
- Inventory of what's currently running (Phase 1).

### Prowlarr indexers (2026-07-28)
- **EZTV was failing**: "blocked by CloudFlare Protection". Root cause: FlareSolverr was never
  wired into Prowlarr (proxy + tag missing) — it had been failing since Feb, not caused by the
  earlier FlareSolverr removal. Fix: redeployed FlareSolverr (`/volume1/docker/flaresolverr`,
  :8191) AND created Prowlarr Indexer Proxy "FlareSolverr" (host http://192.168.68.56:8191)
  with tag `flaresolverr`, then tagged EZTV (and 1337x) with it. EZTV now returns results.
- **Added TV indexers**: LimeTorrents, Knaben, 1337x (1337x tagged flaresolverr).
- Verified aggregate TV search ("the bear s03e01") = 59 seeded results:
  Pirate Bay 26, Knaben 18, LimeTorrents 10, 1337x 3, EZTV 2.
- Note: 1337x adds ~12s/search (Cloudflare challenge each query). Disable if searches feel slow.
- **Pruned for speed (2026-07-28):** removed **1337x** (3.3s warm / ~12s cold Cloudflare challenge
  for only ~3 results — gated every search) and **BTdirectory** (broken: btmulu.live Cloudflare-
  blocked, returned errors). Search time dropped ~12s → **0.8–2.2s** with only 3 fewer results.
  Final set: The Pirate Bay (~26), Knaben (~18-21), LimeTorrents (~10-28), EZTV (TV, via
  FlareSolverr), YTS (movies). RULE OF THUMB: Cloudflare-protected indexers are slow — only keep
  them if they add unique content (EZTV does; 1337x didn't).

### Audiobooks (2026-07-28)
- **Readarr is RETIRED** (Servarr archived it; metadata provider dead). Confirmed: lookup for a
  known title returns 0 results. It still manages the existing 1360 books but CANNOT add new ones.
  Fixed its download client anyway (was pointing at 192.168.68.58 — a machine that isn't the NAS;
  it got missed when Sonarr/Radarr/Prowlarr were repointed) → now 127.0.0.1:8080, test OK.
- **Workflow instead:** Prowlarr manual search → grab with qBittorrent category **`audiobooks`**
  → lands in `/volume1/Media/Audio/to_tag` (ABS staging) → tag/organize → move to
  `Audio/Regular/<Author>/<Title>` (the ABS library `/Audio`).
- Added mount `/volume1/Media/Audio/to_tag:/audiobooks` to qBittorrent + category `audiobooks`.
- **GOTCHA (cost an outage):** thrnz uses PIA codes like `ca_toronto`; **`ca_montreal` is INVALID**
  and the container hard-fails ("Location not found") → qBittorrent then never starts because it
  waits on the VPN healthcheck. Keep LOC=ca_toronto.
- Audiobook indexers: 78 audiobook-capable in Prowlarr but nearly all PRIVATE. Public options are
  effectively Knaben + The Pirate Bay (both already added). MyAnonaMouse (interview-based) is the
  realistic upgrade if Pat wants a real audiobook library.
- **If joining a private tracker:** current seed policy (ratio 1.0 / 3 days then *arr deletes)
  would break ratio rules — must exempt those torrents (separate category, no seed limit) FIRST.
- Audiobookshelf: user `imnotlytle`, password reset to admin123 (bcrypt via the container's
  /server/libs/bcryptjs; DB backed up). App URL: https://abs.patplex.net (works home + away).

### Audiobookshelf "stream error undefined" — stale DB paths (2026-07-28)
- Symptom: web player threw "stream error undefined"; many books missing from ABS.
- Root cause: the Stephen King collection had been RENAMED on disk to
  `YYYY - Title (read by Narrator)` but ABS never rescanned. 63/137 items pointed at folders
  that no longer existed; 68 folders on disk were unindexed. ffmpeg failed because ABS couldn't
  stat the source files, so it never wrote `/metadata/streams/<id>/files.txt`.
- Fix: forced library scan (`POST /api/libraries/<id>/scan?force=1`) → 69 Added / 74 Updated /
  63 Missing; then purged stale entries (`DELETE /api/libraries/<id>/issues`).
  Result: 143 items, 0 missing. Streaming works.
- **DO NOT bulk-rename the library.** Verified ABS parses `YYYY - Title (read by X)` correctly
  into title/narrator/publishedYear (e.g. "2010 - Blockade Billy (novella - read by Craig Wasson)"
  → title=Blockade Billy, narrator=Craig Wasson, year=2010). Plain-title folders (e.g.
  `Frank Herbert/Dune`) yield NO narrator. The King naming is the better convention.
  Renaming also resets listening progress (new item IDs) and requires a rescan.
- LESSON: after ANY folder rename in the audiobook library, run an ABS scan or items go stale.
- Audiobook ORDER audit: `scripts/audiobook-order-check.py`. Real finding = Turtledove "Darkness"
  series has SCRAMBLED track tags (e.g. Into the Darkness: ...11,13,14,15,12,16... so ch15 plays
  before ch12) — still UNFIXED, offered to retag from filenames. King multi-part "gaps" are FALSE
  positives (tracks number continuously across part folders).

### ABS duplicate titles fixed (2026-07-28)
- ABS derives a book's title from the **`album` tag**, not the folder name. Duplicates came from:
  - 5 Turtledove books tagged `album=Darkness` (Through/Rules/Out of/Jaws of/Darkness Descending)
    all displayed as one title. ("Into the Darkness" had the correct album tag, hence no dupe.)
  - King anthology novellas (Different Seasons x4, Four Past Midnight x4) inherited the anthology
    album tag; each novella is a separate library item so they looked like duplicates.
- Fixed via ABS API `PATCH /api/items/<id>/media {"metadata":{"title":...}}` — 14 targeted edits,
  no files touched. Result: 143 items, **0 duplicate titles**.
- A broad "derive title from folder name" rule was DRY-RUN first and REJECTED — it would have
  wrecked good metadata (e.g. "The Dark Tower VII: The Dark Tower" -> "The Dark Tower",
  "2001: A Space Odyssey" -> "2001 A Space Odyssey"). Only genuine duplicates were changed.
- Format audit: 2 single-file m4b, 59 multi-file m4b, 62 multi-file mp3, 0 mixed. All codecs are
  aac/mp3 = ABS direct-streams them (`-c:a copy`). **Nothing requires conversion for playback.**
  Merging multi-file books into single chaptered m4b (via m4b-tool; Pat has an auto-m4b-tool.log)
  is optional polish only — expensive on the N100 CPU.
