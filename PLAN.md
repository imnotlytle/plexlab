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
- ~~Radarr profile 7 has no DV/Atmos/HDR10+ scores~~ — **DONE 2026-08-05**, scored to match Sonarr.
- **Radarr profile 7 YTS scores pull against the DV preference** — +500/+1000 for YTS (small, low
  bitrate) on the same profile that now prefers DV. Decide which way that profile should lean.
- **Recyclarr needs a profile to manage** (2026-08-05) — installed but its config is a no-op and the
  scheduled container is not started. Now that profile 7 is scored by hand, the question is whether
  Recyclarr should take ownership of that scoring (declarative, cannot drift again) or stay off.
- ~~Vaultwarden `SIGNUPS_ALLOWED=true`~~ — **DONE 2026-08-05**: account created
  (`p.lytle43@gmail.com`, 652 items imported), signups locked. Verified a registration POST now
  returns 422.
- **Vaultwarden only works on the LAN** — `vault.patplex.net` resolves via the AdGuard rewrite and
  is NXDOMAIN publicly, so the browser extension and phone app cannot reach the vault away from
  home. With 652 passwords in it that will be felt. Options: a WireGuard/Tailscale tunnel back home
  (keeps the vault unexposed — preferred), or publishing it through the Cloudflare Tunnel behind
  Cloudflare Access (convenient, but puts the vault on the internet).
- **Client gotcha:** self-hosted accounts do NOT exist on `vault.bitwarden.com`. The web vault is
  `https://vault.patplex.net:8443`; the extension and mobile app need
  ⚙️ → Self-hosted → Server URL set BEFORE logging in.
- ~~Uptime Kuma has no monitors~~ — **DONE**: 17 monitors + ntfy alerting, both verified.
- **No VPN kill-switch monitor** — needs a script comparing qBittorrent's exit IP to the host's,
  feeding a push monitor. The port check only proves qBittorrent is alive, not that it is tunnelled.
- **Bazarr has no OpenSubtitles.com account** — three no-account providers only.
- Offsite backup still missing — `/volume1/docker/_backups` is same-pool only.

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

### Audiobook merge to single-file m4b (2026-07-29)
- Converted 133 multi-file audiobooks -> single chaptered .m4b. Ran on **Pat's PC**
  (Ryzen 7800X3D) against the NAS over SMB — the N100 is far too slow. ffmpeg installed on the
  PC via winget (Gyan.FFmpeg). Script: `scripts/Merge-Audiobooks.ps1` + `Run-MergeOvernight.ps1`.
- Phase 1 (AAC, lossless stream copy): 51 books in 87 min. Phase 2 (mp3->aac transcode): ~8.7 hrs.
  0 failures. Output 85 GB vs ~145 GB originals (~40% smaller). Output: `/volume1/Media/Audio/merged`.
- **Originals untouched.** Nothing deleted/moved.
- THREE bugs found and fixed in the script during the run:
  1. Book boundaries were folder-depth based -> was fusing Southern Victory's 11 novels into one
     4.5 GB file. Fixed by driving the merge from **ABS's own library relPaths** (`scripts/absbooks.txt`).
  2. Sorting preferred track tags -> the Turtledove "Darkness" books have SCRAMBLED tags, which
     would have baked the wrong chapter order in permanently. Now prefers a clean filename
     sequence and logs when tags disagree. All 6 Darkness books verified CORRECT order.
  3. Sequence detection grabbed the last number in the filename — ".m4b"/".mp3" contain digits,
     so every file scored the same. Now strips the extension first.
- PowerShell gotcha: never use `-stats` / `2>&1` on ffmpeg in PS 5.1 — stderr becomes
  NativeCommandError and the script "fails" on success.
- **Audiobookshelf adopted into compose** (`docker/audiobookshelf/`, container still `MsCobel`).
  Added `/merged` mount + **`/metadata` mount** (it previously had METADATA_PATH set with NO
  volume, so all cover art/cache/ABS-backups lived in the container layer and would vanish on any
  recreate; 38 MB copied out to `/volume1/Config/AudioBookShelf-metadata` first).
- Second library "Audiobooks (merged test)" -> `/merged`, 133 items, for side-by-side testing
  before any swap. Swap plan: verify -> move originals to `_originals` -> promote merged ->
  delete originals after a confidence period. NOTE: swapping resets listening progress.

### Audiobook library swap COMPLETE (2026-07-29)
- All 138 multi-file books merged (0 failures) + the 5 already-single-file books COPIED into
  `/volume1/Media/Audio/merged` so the merged set is complete at 143 = same as the original.
- Swap method (non-destructive): deleted the OLD ABS library *definition* and renamed
  "Audiobooks (merged test)" -> "Audiobooks" pointing at `/merged`. **No files were moved or
  deleted** — originals remain at `/volume1/Media/Audio/Regular` (90 GB) until Pat removes them.
  Revert = re-add `/Audio` as a library. DB backed up as `absdatabase.sqlite.pre-swap.*`.
- Final: 143 books, ALL single-file, 140 with chapters, 2132 hours, 0 duplicate titles.
- GOTCHA: the merged .m4b files did NOT inherit album/artist tags (ffmpeg `-map_metadata 1`
  pulled only the chapters file), so ABS fell back to folder-name parsing and 62 titles showed
  raw folder text ("Blaze (read by Ron McLarty)", "1_ Rita Hayworth..."). Fixed via the ABS API.
  If ever re-merging, use `-map_metadata 0` on the concat input to carry source tags through.
- **CORRECTION to an earlier claim:** this did NOT save ~40% space. Originals 89.1 GB vs merged
  89.2 GB — essentially identical (most books were already AAC = stream copy; mp3->aac at 96-128k
  lands at a similar size). The real wins are: one file per book, working chapters, and the
  Turtledove scrambled-order bug permanently fixed.

### Cover audit (2026-07-29)
- Method: exported every cover, built contact sheets, and VIEWED them; verified suspects
  individually (contact-sheet index mapping proved unreliable — ffmpeg's image2 sequence reader
  skipped frames, so only per-file verification is trustworthy).
- 141/143 books have a cover file; 2 have none (Cycle of the Werewolf, Jaws of Darkness).
- **8 CONFIRMED WRONG covers** — ABS auto-match takes the FIRST provider result, which for
  ambiguous titles grabs an unrelated book:
  | Book | Cover it wrongly got |
  |---|---|
  | Into the Darkness (Turtledove) | "Lights Out" - Navessa Allen |
  | Out of the Darkness (Turtledove) | "Lights Out" - Navessa Allen |
  | Darkness Descending (Turtledove) | "Everi: Darkness Descending" - Averi Sayer |
  | Rules of the Darkness (Turtledove) | "Rules of Darkness" - Jack Hunt |
  | Through the Darkness (Turtledove) | "Stone Lands" - Fiona Robertson |
  | Days of Infamy (Turtledove) | "End of the Beginning" (its own sequel) |
  | Hyperion (Simmons) | "The Fall of Hyperion" (its own sequel) |
  | Apt Pupil (King novella) | "The Dark Tower II" |
- FIXED automatically: **Hyperion** (exact Audible match existed; ABS had just picked result #1).
- NOT fixable via providers: the Turtledove Darkness series is essentially unindexed —
  Audible returns only Navessa Allen books regardless of author, Google/OpenLibrary return
  nothing, FantLab has the correct book but only a Russian-edition cover.
  Script: `scripts/fix-abs-covers.py` (`--strip` clears wrong covers when no correct one exists).
- COVERAGE CAVEAT: ~60 books visually verified + the 8 suspects. The remaining ~80 were not
  reliably checked because of the contact-sheet offset issue.

### Cover audit COMPLETE — all 143 books visually verified (2026-07-29)
- Method that works: `scripts/build-cover-grids.py` builds contact grids with EXPLICIT ffmpeg
  `-i` inputs + xstack, and writes a `grid_NN.txt` cell->title map. (The earlier attempt used
  the image2 sequence reader `-start_number`/`%03d`, which silently skips frames and made the
  mapping wrong by 5 positions — never use it for this.)
- **15 wrong covers found and fixed** across two rounds:
  Round 1 (7 Turtledove + Hyperion): Into the Darkness, Out of the Darkness, Darkness Descending,
  Rules of the Darkness (actual book = "Rulers of the Darkness"), Through the Darkness,
  Jaws of Darkness, Days of Infamy, Hyperion.
  Round 2 (found by the full visual audit): Rage (had "Road Rage"), Rita Hayworth and the
  Shawshank Redemption (had "Le Fleau" = French "The Stand"), Storm of the Century (had a
  Willie Drye hurricane history), The Art of War (had an MJ DeMarco business book),
  The Breathing Method (had Dark Tower IV), The Dark Tower (had DT1 Gunslinger),
  The Shining (had Doctor Sleep, its sequel).
- Sources: `scripts/apply-archive-covers.py` + `scripts/fix-covers-round2.py`. Audible only when
  title AND author both match; otherwise archive.org `/services/img/<identifier>` (rejecting
  <3 KB 1x1 placeholders). One cover came from Wikipedia (Into the Darkness cover art).
- **openlibrary.org is DOWN** (connection refused on 443 from both NAS and PC; DNS resolves fine,
  AdGuard is NOT blocking it). ABS's OpenLibrary provider will recover on its own.
- Acceptable-but-imperfect (left alone): novellas (The Langoliers, The Library Policeman,
  The Sun Dog, Secret Window) show their parent "Four Past Midnight" cover; "Throttle" shows the
  "He Is Legend" anthology it appeared in; "Morality" uses the Esquire issue it was published in;
  "Night Shift" shows a single-story "Graveyard Shift" edition; "The Time Machine" shows a sci-fi
  mega-collection. All are the correct work, just not a dedicated cover.
- Still missing a cover entirely: Cycle of the Werewolf.

### Ebook server — Calibre-Web Automated (2026-07-29)
- `docker/calibre-web/` -> `/volume1/docker/calibre-web`, UI on **:8083**, memory-capped 1500M.
  Library `/volume1/Media/Books/library`, auto-ingest folder `/volume1/Media/Books/ingest`
  (drop any ebook there and it is imported + organised by author automatically).
- Login: **admin / admin123** (verified) — change at `/me`.
- Sharing (verified URLs, all return 302 = exist):
  * **OPDS** works out of the box, no setting: `http://192.168.68.56:8083/opds` (401 without auth).
  * **Kobo Sync** — I enabled it (`config_kobo_sync` 0 -> 1 in `/volume1/Config/calibre-web/app.db`,
    container must be stopped to edit). Per-user token at `/admin/view` -> click user.
  * **Send to Kindle** — needs SMTP at `/admin/mailsettings` (still placeholder mail.example.org).
  * **New users** at `/admin/user/new`.
- Bulk import: `scripts/import-standard-ebooks.py` (Standard Ebooks = public-domain classics,
  professionally typeset, free/legal). ~1198 books found.
  GOTCHAS: `/downloads/*.epub` returns an HTML interstitial — must append `?source=download`;
  the OPDS feed `/feeds/opds/all` is 401 (patron-only) so scrape the public `/ebooks` listing;
  a browser User-Agent is required; and SE rate-limits (HTTP 429) — use >=3s delay plus
  exponential backoff or the run dies around book ~316.
- SIZE REALITY: ebooks are tiny. All ~1200 Standard Ebooks ~= 1 GB; all of Project Gutenberg
  (~75k books) ~= 15 GB. The 500 GB budget is ~50x more than this needs.
- Gutenberg mirrors reachable for future bulk import: gutenberg.pglaf.org,
  mirrors.xmission.com/gutenberg, mirror.csclub.uwaterloo.ca/gutenberg (aleph.gutenberg.org is not).
- "Overseerr for books" = **Calibre-Web Automated Book Downloader** (searches Anna's Archive /
  LibGen, drops into the ingest folder). Self-serve, no request/approve workflow. NOT installed —
  flagged the copyright consideration to Pat first.

### Ebook library: curated Gutenberg + public tunnel (2026-07-29)
- **Gutenberg curation decision:** the full text-only EPUB mirror is 78,008 books / 19.2 GB
  (rsync `aleph.gutenberg.org::gutenberg-epub`). NOTE the full mirror incl. `-images` variants is
  **269 GB**, and rsync filter ORDER matters — excludes must come BEFORE includes or the
  `-images` files match first. Abandoned the full pull (mirror throttles to ~250 kB/s = ~26 h)
  in favour of `scripts/import-gutenberg-top.py`, which pulls Gutenberg's published
  **top-1000 by download count** — the best available proxy for "classics people actually read"
  (their bookshelves are broad categories, not quality lists). Downloads via the pglaf mirror,
  per Gutenberg's robot policy.
- **Public tunnel:** added `books.patplex.net` -> `http://192.168.68.56:8083` as a published
  application route on the Overseerr tunnel (`d22066e0`) via the CF dashboard. Verified live
  (HTTP 200, serves the Calibre-Web login). The tunnel now publishes THREE hostnames:
  overseerr / abs / books.
- **book-downloader deliberately NOT tunnelled** — bound to `192.168.68.56:8084` (LAN only).
- DNS: `calibre.home` added for Calibre-Web. NOTE `books.home` already existed pointing at the
  NAS for Audiobookshelf, so remember the ports: calibre.home:8083 = ebooks,
  books.home:13378 = audiobooks.

### Shelfmark (book-downloader) wired to Prowlarr + AudiobookBay (2026-07-29)
- Image is `calibre-web-automated-book-downloader` but the app brands itself **Shelfmark** (v1.3.4).
- Flow: Prowlarr (indexers) -> qBittorrent -> Shelfmark imports -> `/cwa-book-ingest` -> Calibre-Web.
- **CRITICAL path rule (from Shelfmark's own docs):** Shelfmark must see download files at the
  SAME container path the download client reports. qBittorrent maps
  `/volume1/Media/temp/downloads -> /downloads`, so Shelfmark now mounts the identical host path
  at `/downloads`. Verified it can see the real files. (Same class of bug that broke Radarr imports.)
- Env set: `PROWLARR_ENABLED/URL/API_KEY/AUTO_EXPAND`, `PROWLARR_TORRENT_CLIENT=qbittorrent`,
  `PROWLARR_TORRENT_ACTION=keep` (keeps seeding; qBit's own ratio 1.0 / 3-day limits still apply),
  `QBITTORRENT_URL/USERNAME/PASSWORD`, `ABB_ENABLED=true` + `ABB_HOSTNAME`.
- Secrets in gitignored `/volume1/docker/calibre-web/.env` (chmod 600): Prowlarr API key,
  qBittorrent creds, ABB hostname. Config dir `/volume1/Config/shelfmark`.
- Verified from inside the container: Prowlarr 302, qBittorrent 200, ABB host 200.
- Still LAN-only (`192.168.68.56:8084`), deliberately NOT on the Cloudflare tunnel.
- **"Open Library not enabled" error:** `METADATA_PROVIDER` defaults to `openlibrary` but the
  provider itself ships DISABLED, so every search errors until `OPENLIBRARY_ENABLED=true` is set.
  Also enabled Google Books as a fallback (openlibrary.org had a hard outage — connection refused
  on :443 — earlier the same day; it has since recovered). `GOOGLEBOOKS_API_KEY` is optional and
  only raises the free quota; the provider works without one.

### Shelfmark: split routing + auth + public exposure (2026-07-29)
- **Ebook vs audiobook routing now separated:**
  | type | qBit category -> save path | Shelfmark dest | library |
  |---|---|---|---|
  | ebooks | `books` -> `/downloads/books` | `/cwa-book-ingest` | Calibre-Web |
  | audiobooks | `audiobooks` -> `/downloads/audiobooks` | `/audiobooks` | Audiobookshelf staging (`Audio/to_tag`) |
  Env: `INGEST_DIR`, `DESTINATION_AUDIOBOOK`, `QBITTORRENT_CATEGORY`, `QBITTORRENT_CATEGORY_AUDIOBOOK`.
  Also set `BOOK_LIBRARY_URL` / `AUDIOBOOK_LIBRARY_URL` for in-app nav buttons.
- **CAUGHT A CONFLICT:** the qBittorrent `audiobooks` category originally saved to `/audiobooks`,
  which is the SAME host folder as Shelfmark's audiobook DESTINATION (`Audio/to_tag`). qBit would
  have downloaded straight into the library and Shelfmark's import would be a no-op, with torrents
  left seeding from inside the library. Fixed by moving both categories under `/downloads/*` so
  source and destination are distinct.
- **AUTH (was `none` = no login at all!):** set `AUTH_METHOD=cwa` + `CWA_DB_PATH=/auth/app.db`
  with `/volume1/Config/calibre-web` mounted at `/auth`, so Shelfmark shares Calibre-Web's user
  database — one account per person covers both. Verified enforced: `/api/status` and
  `/api/settings` return 401 without credentials, publicly and locally.
- **Exposed publicly** at `https://shelfmark.patplex.net` (4th route on the Overseerr tunnel).
  Port binding changed from LAN-only back to `8084:8084` so the tunnel can reach it.
- ⚠️ The credential now guarding an internet-facing download tool is Calibre-Web's
  `admin`/`admin123` — MUST be changed.

### Audiobook organisation fix + Shelfmark auth auto-restart (2026-07-29)
- **"Audiobooks not moving" was two separate things:**
  1. NOT a bug — the two books in question (`It`, `Boy's life`) were still `downloading`. Fatherland
     (13 files) and The Passage had already transferred fine.
  2. A REAL bug — `FILE_ORGANIZATION_AUDIOBOOK` was `rename`, which dumps files FLAT into the
     destination. Audiobookshelf treats a folder as a book, so a flat multi-file audiobook is
     unusable. Set to `organize` → uses `TEMPLATE_AUDIOBOOK_ORGANIZE={Author}/{Title}/{Title}`.
     Also set `HARDLINK_TORRENTS_AUDIOBOOK=false` (defaulted TRUE; /downloads and /audiobooks are
     separate bind mounts so every hardlink failed EXDEV and fell back to copy anyway, and their
     docs say don't hardlink into a library folder).
  - Retro-fixed the already-flat files into `Robert Harris/Fatherland/` and `Justin Cronin/The Passage/`.
- **NOTE:** qBittorrent category save paths (`/downloads/audiobooks`) are ignored because
  Automatic Torrent Management is off, so everything saves to `/downloads` root. Harmless —
  Shelfmark scans `/downloads` and still finds them — but that's why the subfolders stay empty.
- **Auth auto-restart:** `scripts/shelfmark-auth-watch.sh` watches `app.db`'s mtime and restarts
  `book-downloader` when it changes, so adding a Calibre-Web user no longer needs a manual restart.
  Debounced (20 s settle) and rate-limited (90 s) so routine DB writes don't cause restart loops.
  Logs to `/volume1/docker/_backups/shelfmark-auth-watch.log`.
- **Audiobooks now land directly in the LIVE library.** `DESTINATION_AUDIOBOOK=/audiobooks` was
  mounted to `Audio/to_tag` (staging), so every download still needed a manual move. Remounted to
  `/volume1/Media/Audio/merged` — the folder ABS actually scans. Safe because
  `FILE_ORGANIZATION_AUDIOBOOK=organize` writes `{Author}/{Title}/`, matching the library layout,
  and ABS's file watcher is on (`scannerDisableWatcher=false`) so new books appear automatically.
  Verified Shelfmark can write there (38 existing author folders visible).
- Note: Fatherland + The Passage ended up duplicated (Pat had already moved them into the library;
  a redundant copy remained in `to_tag`). ~2.4 GB reclaimable by deleting the `to_tag` copies.

## Security review (2026-07-29)

Audited the whole server: what's internet-exposed, auth on each, container privileges, LAN port
bindings, secret file permissions.

**Good news — all four public services correctly reject unauthenticated API calls (401):**
overseerr / abs / books / shelfmark. Root pages return 200 (SPA shells), which is expected.

**Fixed:**
1. **World-readable secrets.** `/volume1/docker/vpn-qbittorrent/.env` (PIA username+password) and
   `minecraft-atm9/data/.rcon-cli.env` were both mode **777**. Now 600. The PIA one had been set
   to 600 originally — an overwrite via `cat >` reset it, so re-check after any redeploy.
2. **Orphaned Portainer agent removed.** `portainer_agent` held a **read-write Docker socket**
   (effectively root on the host), had **zero** connections in the previous week, and no Portainer
   server was running anywhere. Pure attack surface — removed, port 9001 closed.
3. **FlareSolverr un-exposed.** It was on `0.0.0.0:8191` — an unauthenticated headless browser
   reachable from any device on the LAN (SSRF risk), and not even wired into Prowlarr
   (IndexerProxies empty). Rebound to `127.0.0.1:8191`. Prowlarr runs host-network so it can still
   reach it; verified LAN access now fails (000) while localhost returns 200.
   NOTE: when wiring it in Prowlarr, use `http://127.0.0.1:8191`, NOT the LAN IP.
4. **Weak password on an internet-facing service.** Audiobookshelf was reachable at
   `abs.patplex.net` with `imnotlytle`/`admin123` — verified exploitable from the public internet
   (login returned 200). Changed to Pat's chosen password; old one now 401.

**Known/accepted:**
- The *arr containers carry broad linuxserver default capabilities (CHOWN, DAC_OVERRIDE, SETUID…).
  Not internet-exposed; changing them risks breaking the images. Left as-is.
- `wireguard-pia` needs NET_ADMIN — required for the tunnel, expected.
- `diun` has a READ-ONLY docker socket — needed to read image tags, acceptable.
- LAN-exposed with no auth: `firefox-app-1` (5888/5999), `maintainerr` (6246), `tautulli` (8181),
  `adguardhome` (3000). All LAN-only; a consumer router means no VLAN isolation available.
- Passwords are now reused across services. Better than `admin123` but distinct passwords would
  be stronger.

**Not done / worth considering:**
- Cloudflare Access or WAF rate-limiting in front of the public hostnames (would harden against
  credential stuffing, but can break the Audiobookshelf/Prologue mobile apps).
- Offsite backup still missing — `/volume1/docker/_backups` is same-pool only.

### Credentials moved out of the repo (2026-07-29)
Prep for publishing this repo. Five scripts had hardcoded logins
(`qbit-port-sync.sh`, `watch-audiobook-imports.sh`, and the three cover scripts). They now read
`/volume1/docker/scripts/.creds` (chmod 600, gitignored). Two benefits: nothing sensitive is
tracked, and the cover scripts no longer carry a STALE Audiobookshelf password (they would have
failed after the security rotation). Verified both cron-driven scripts still authenticate.
STILL IN THE REPO if it ever goes public: the real domain (patplex.net), LAN IPs, Cloudflare
account/tunnel IDs, and the ABS username. Fine for a private repo; scrub before publishing.

### Shelfmark auto-import is NOT reliable for in-flight downloads
`The Postman` finished and was left in `/downloads` with **no post-processing attempt logged at
all**. Cause: Shelfmark tracks downloads as in-memory tasks, and this session restarted the
container repeatedly for config changes, orphaning every task that was already running. Those
torrents complete with nobody watching them.
- Downloads STARTED AFTER the last restart should auto-import correctly.
- Anything already in flight during a restart needs manual import.
- `scripts/watch-audiobook-imports.sh` exists to make this visible — it flags
  `[NOT IMPORTED]` per finished torrent rather than failing silently.
Manually imported so far: Wool, Boy's Life, It, The Postman.

### Sonarr "not auto-grabbing" was actually MALWARE PROTECTION (2026-08-01)
- Symptom: Silo S03E05 aired 2026-07-31 and never appeared. Automation looked broken.
- Reality: Sonarr **did** grab it (2026-07-30 21:15, `Silo S03E05 MULTI 1080p WEB H264-HiggsBoson`),
  the download completed, and Sonarr then **refused to import it**:
  `"Caution: Found executable file with extension: '.exe'"`.
- Inspected the payload: the entire 1.2 GB "episode" was a SINGLE Windows executable,
  `Silo S03E05 MULTI 1080p WEB H264-HiggsBoson.exe` — no video file at all. Straight malware
  disguised as a TV release. Sonarr's protection worked exactly as intended.
- Removed from the queue with `removeFromClient=true&blocklist=true` (deletes files AND stops
  Sonarr re-grabbing that release). Verified no `.exe` remains in /downloads.
- LESSON: an episode stuck at `importPending` with a `statusMessages` warning is worth reading —
  it is often a rejected-for-a-reason release, not a stuck import. `MULTI` releases from unknown
  groups are a common malware vector.
- Follow-up: Silo uses quality profile **7 ("Ultra HD/1080p")**, but the Dolby Vision / Atmos /
  HDR10+ custom formats had only been scored on profile **5**. Added them to profile 7
  (DV 1500 / Atmos 400 / HDR10+ 300) so this show now prefers DV+Atmos automatically.
  Re-searched and grabbed `Silo S03E05 Memory 2160p ATVP WEB-DL DDP5.1 Atmos DV HDR` (9.8 GB).
- NOTE: the earlier lean-1080p size tuning (max ~45 MB/min) now rejects 4 GB 1080p releases like
  CAKES as "larger than maximum allowed 2.3 GB". Fine while targeting 2160p for this show, but
  that limit is why some 1080p releases get skipped.

### AdGuard hardening — blocklists + bypass prevention (2026-08-01)
Symptom: "ads still showing on a recipe site". Diagnosis found AdGuard was working correctly the
whole time (all major ad networks resolving to 0.0.0.0), and the desktop's Wi-Fi "ISP DNS" was a
red herring — **the Wi-Fi adapter is Disconnected**, so those were stale profile values, never in
use. Ethernet was on AdGuard throughout. The ads were first-party (served from the site's own
domain), which DNS blocking cannot distinguish from content.
- Was running the DEFAULT blocklist only (~161k rules). Added OISD Big (330,788),
  HaGeZi Multi PRO (216,256), AdAway (6,540), HaGeZi Windows-Office Tracking (389).
- **Added HaGeZi DoH-VPN-Proxy Bypass (17,536 rules)** — blocks `dns.google`,
  `cloudflare-dns.com`, `dns.quad9.net`, Mozilla's resolver etc. so a device with encrypted DNS
  baked in CANNOT bypass AdGuard; it falls back to the network resolver. This is what makes the
  blocking actually network-wide rather than opt-in.
  VERIFIED SAFE: AdGuard's own upstreams are those same hostnames, but it reaches them via
  bootstrap IPs, so blocking them for clients does not break resolution. Confirmed google.com,
  github.com, netflix.com, plex.tv, amazon.com all still resolve with 0 upstream errors.
- **Total: 733,298 rules** (up from ~161k).
- CEILING (architectural, not fixable by config): DNS cannot block YouTube/Twitch/Facebook in-feed
  ads or first-party ads — they share a domain with the content. uBlock Origin in the browser is
  the complement; AdGuard covers devices that can't run an extension.

### iCloud Private Relay was bypassing AdGuard on the iPhone (2026-08-01)
Per-client stats showed the iPhone (192.168.68.52) at **4.4% blocked** vs the PC at 58.6%. Its top
queries were `mask.apple-dns.net` and `mask.icloud.com` — **iCloud Private Relay**, which tunnels
Safari traffic through Apple's proxy and bypasses network DNS entirely.
- The HaGeZi bypass list already blocked `mask.icloud.com`/`mask-h2.icloud.com`, but with the
  default `0.0.0.0` response, and `mask.apple-dns.net` was still resolving — so the fallback was
  half-applied and ungraceful (device waits for a connect timeout).
- Apple's DOCUMENTED method for a network to disable Private Relay is to return **NXDOMAIN**.
  Added user_rules:
    `||mask.icloud.com^$dnsrewrite=NXDOMAIN`
    `||mask-h2.icloud.com^$dnsrewrite=NXDOMAIN`
    `||mask.apple-dns.net^$dnsrewrite=NXDOMAIN`
  Verified all three return NXDOMAIN; apple.com / icloud.com / google.com / netflix.com unaffected.
  Private Relay fails OPEN — connectivity is not broken, iOS just shows a one-time notice.
- GOTCHA writing these rules: the rule text contains `||` and `^$`, which breaks a `sed` using `|`
  as delimiter AND gets mangled through ssh→docker nested heredocs. Write the edit to a script file
  first, mount /tmp into the throwaway container, and use `awk` with `\x27` for quotes.
- Note the other 0%-blocked clients (.54/.55/.62) are NOT a problem — they are idle devices making
  only legitimate Apple/Google/Home-Assistant queries.
- Browser-layer plan: uBlock Origin on desktop; **Brave on iOS** (Pat doesn't use Safari, and iOS
  content blockers only work in Safari — Brave has blocking built in and also kills in-app YouTube ads).

### Why a newly added show doesn't download itself (2026-08-01)
Sonarr's **RSS Sync only sees NEWLY POSTED releases** — it polls indexers every 15 min for what has
appeared since the last check. It never searches the back catalogue. So a show whose episodes
already aired stays at 0 files forever unless a search is explicitly triggered.
- **Fix:** tick **"Start search for missing episodes"** in the Add Series dialog. Without it,
  Sonarr adds the series and waits for future episodes only. (Dark Winds was added 2026-08-01 with
  0/34 and sat idle for exactly this reason; ran a SeriesSearch manually.)
- **Reading the counts:** Sonarr's `totalEpisodeCount` includes unaired episodes AND specials, so
  "Better Call Saul 63/273" is NOT a 200-episode gap. Use `/wanted/missing` filtered to
  `airDateUtc < now` for the real number.
- Actual backlog at this point: **358 aired-but-missing episodes across 11 shows** — dominated by
  Black Clover (170) and The Walking Dead (110). Pat chose NOT to bulk-search these.

### Full container update + media stack adopted into compose (2026-08-03)
Updated every container. Split by how each was managed:
- **12 compose-managed** — straightforward `docker compose pull && up -d`. Updated: tautulli,
  book-downloader, calibre-web, audiobookshelf, cloudflared-media, flaresolverr, qbittorrent,
  wireguard-pia. (adguard/maintainerr/diun were already current.)
- **6 GUI-created with NO compose file** (Sonarr, Radarr, Readarr, Prowlarr, Overseerr, Plex) —
  these were the ones showing updates. **Adopted into `docker/media/docker-compose.yml`**, so
  future updates are one command instead of a hand-rebuild. Original container names preserved
  (`linuxserver_sonarr-1`, `PatPlexProwlarrv2`, `DefiantJazz`, …) so nothing referencing them breaks.

**Pre-update safety:** captured full `docker inspect` of all six to
`/volume1/docker/_backups/container-specs/`, and verified today's ROOT cron backup contained the
files a user-run backup cannot read (AdGuard config, PIA token, Plex config, *arr DBs).
NOTE: running `backup-configs.sh` as the normal user exits rc=2 and SKIPS those root-owned paths —
the cron copy (which runs as root) is the complete one.

**Two things that had to be preserved and were verified after:**
1. **Plex `/dev/dri` passthrough** — Intel QuickSync on the N100. Losing it silently drops Plex to
   CPU transcoding. Confirmed `card0` + `renderD128` present in the new container.
2. **VPN kill-switch** — re-tested after updating wireguard-pia/qbittorrent: exit IP is PIA's,
   and stopping the tunnel leaves qBittorrent with zero egress. Port forwarding re-synced.

**Readarr deliberately left PINNED** at `0.4.11-nightly` (retired upstream; `:latest` is unmaintained).

**Post-update verification:** Sonarr 4.0.19.2979 and Radarr 6.3.0.10514 both connection-test OK to
qBittorrent; Prowlarr 2.5.2.5491 kept all 5 indexers; Plex serves all 3 libraries; all four public
hostnames return 200; DNS and ad-blocking unaffected.

### RAM reclaim + five new services (2026-08-05)

**The box was memory-bound, not disk-bound.** Measured before touching anything: 7691 MB total,
**2156 MB available, with 3249 MB of swap already in use** — while disk sat at 48% (12 TB free).
The 19 running containers accounted for only ~2.0 GB; the rest is UGOS Pro itself. Every decision
below follows from that number.

**Phase 0 — reclaimed 348 MB** (measured: available 2156 → 2504 MB, swap 3249 → 2932 MB):
- **`firefox-app-1` REMOVED.** 260 MB, `restart=always`, running since 2026-07-05, created Feb 2025.
  It published `0.0.0.0:5888` (browser) and `0.0.0.0:5999` (VNC) — unauthenticated, LAN-reachable.
  The 2026-07-29 security review had flagged it and left it. Verified afterwards: no listeners on
  either port. Spec saved to `_backups/container-specs/firefox-app-1.20260805.json` first.
- **Readarr STOPPED, not deleted** (108 MB) — `restart=no`, config untouched at `/volume1/Config`.
  It is retired upstream and only kept for its 1360-book DB; start it on demand if that is needed.
- Also chmod 600'd everything in `_backups/container-specs/` — `docker inspect` output embeds
  container environment variables, and those files were mode 777.

**Bazarr (`docker/bazarr/`, :6767)** — subtitles for the Sonarr/Radarr libraries. Mounts `/TV` and
`/Movies` copied verbatim from the media stack so paths align; verified `docker exec bazarr ls /TV`
returns the same listing Sonarr sees. Wired to both apps by reading their API keys straight out of
`config.xml`. English profile created, set as default for new items, and back-filled onto all
existing items (47 series, 600 movies — 0 left unassigned).

- **GOTCHA THAT COST THE MOST TIME HERE:** the first language profile was written without the
  `audio_only_include` key. The profile *saved fine* and the UI looked correct, but
  `subtitles/indexer/movies.py:253` reads that key unconditionally, so every "index missing
  subtitles" pass died with `KeyError: 'audio_only_include'` and returned HTTP 500. Bazarr therefore
  never worked out what was missing — it looked installed and did nothing. Symptom to recognise:
  POSTs to `/api/movies` return 500 while the profile assignment itself still lands. Full item
  schema is `id, language, audio_exclude, audio_only_include, hi, forced`.
- Second gotcha: language profiles are NOT saved via `/api/system/languages/profiles` (GET-only,
  POST returns 405). They go through `POST /api/system/settings` with the `languages-profiles` and
  `languages-enabled` form keys.
- Third: shell/grep parsing of Bazarr's JSON undercounts badly (titles contain braces and commas) —
  it reported 413 movies when there were 572. Use a real JSON parser.
- Providers enabled: podnapisi, tvsubtitles, yifysubtitles — all work without an account.
  OpenSubtitles.com has far better coverage but needs a free login; left for Pat to add.
- Verified working: **197 movies and 71 episodes** now correctly identified as missing subtitles.

**Recyclarr (`docker/recyclarr/`) — INSTALLED BUT DELIBERATELY NOT SCHEDULED.**
Installing it surfaced a live bug it would have prevented:

- **Radarr quality profile 7 "Ultra-HD/1080p" carries 567 of 613 movies (92%) and has NO Dolby
  Vision, Atmos or HDR10+ scores at all.** Those custom formats were scored on profile 5, which
  only 6 movies use. Sonarr's profile 7 *does* have them — added 2026-08-01 when the Silo problem
  was found — but the same fix was never applied to Radarr. **The 4K tuning is effectively inactive
  for the movie library.** Not changed yet: adding scores alters grab/upgrade behaviour for 567
  movies and is Pat's call.
- A stock TRaSH template would have done real damage here. Inspected before running:
  `quality_definition: type: movie` overwrites the lean 1080p sizing (~22 MB/min pref, ~45 max);
  `quality_profiles: trash_id:` CREATES a new profile rather than editing the ones in use; and
  `reset_unmatched_scores: enabled: true` zeroes every score not named in the config — which would
  wipe the YTS/EZTV penalties and the DV/Atmos work.
- Name collisions are real: Radarr and Sonarr each have hand-made formats named exactly
  `Dolby Vision`, `HDR10Plus`, `Atmos`. Recyclarr matches by name, so a sync REPLACES those
  definitions. Scores live on the profile, not the format, so scoring would survive — but the
  matching rules would change.
- Current config is intentionally a **no-op**: `sync --preview` reports "No changes" for both
  instances. Recyclarr only syncs custom format definitions for formats a managed quality profile
  references, so with `quality_profiles:` omitted there is nothing to do. **Open decision** in
  "Open items" below.
- Config gotcha: instance names must be unique across BOTH the `radarr:` and `sonarr:` blocks —
  naming each one `main` fails with "Duplicate Instances". The `[Streaming Services] General` group
  id is Radarr-only; repeating it under Sonarr warns "does not match any known CF group".

**Vaultwarden (`docker/vaultwarden/`, 192.168.68.56:8222)** — closes the review's "passwords are now
reused across services". **LAN-only and NOT on the Cloudflare tunnel** — exposing a password vault
is a separate decision with its own hardening. `SIGNUPS_ALLOWED=true` for first-account creation
and **must be flipped to false** afterwards.

**Uptime Kuma (`docker/uptime-kuma/`, 192.168.68.56:3001)** — nothing previously reported failures;
both the Overseerr scan failure and Shelfmark's orphaned downloads were found by hand, days late.

**Homepage (`docker/homepage/`, 192.168.68.56:3003)** — one dashboard for ~20 services.
`HOMEPAGE_ALLOWED_HOSTS` is REQUIRED on current versions or the page fails host validation. No
docker socket is mounted (same reasoning that removed the Portainer agent); services are listed
explicitly in `services.yaml`.

**Verification:** all three new web services return 200/302 and are bound to `192.168.68.56` only,
never `0.0.0.0` (confirmed with `ss -lnt`). VPN kill-switch re-tested — qBittorrent exits via
`191.96.36.135` vs the NAS host IP `167.237.38.122`. All four public hostnames still serve. Final
memory: **2174 MB available vs 2156 MB at the start** — the reclaim paid for all five additions.
`vmstat` shows swap-in only, no swap-out: not thrashing.

**Deliberately skipped, on RAM grounds:** Immich (needs 6 GB with ML) and Paperless-ngx
(600–900 MB idle, 1.5–2 GB during OCR). Both are the biggest genuine gaps in the setup. The
DXP2800 has a **single** DDR5 SO-DIMM slot, 8 GB stock, officially supported to 16 GB — that
upgrade is what unlocks them.

### Radarr profile 7 scored to match Sonarr (2026-08-05)

Fixed the drift found above. Radarr profile 7 "Ultra-HD/1080p" now carries **Dolby Vision +1500,
Atmos +400, HDR10+ +300**, matching Sonarr's profile 7. Profile JSON backed up first to
`_backups/container-specs/radarr-profile7.20260805-193014.json`.

- **Zero blast radius on existing files, and this was verified before applying, not assumed:**
  profile 7 has **`upgradeAllowed: False`**. Radarr therefore never re-grabs the 560 existing files
  on that profile — the new scores only decide which release wins on FUTURE grabs. The apply script
  aborts if `upgradeAllowed` is ever True.
- **Worth a later decision:** profile 7 also scores **YTS 1080p +500 and YTS 2160p +1000**, i.e. it
  actively prefers YTS releases, which are small and low-bitrate. Profile 5 does the opposite
  (YTS 2160p **−200**, demoted on 2026-07-27 as a 4K-quality decision). With DV now at +1500 a
  DV release outranks a YTS one, so the intent is served — but profile 7 still pulls in two
  directions. If 4K quality matters more than file size on this profile, the YTS scores should come
  down; if it is meant to be the lean/small tier, they should stay. Not changed either way.

### Uptime Kuma monitors seeded (2026-08-05)

Admin account created by Pat; **16 monitors** seeded and all verified reporting UP with real
responses. DB backed up to `_backups/container-specs/kuma.db.pre-seed.*` first.

- Seed lives in `docker/uptime-kuma/seed-monitors.sql`, committed and **idempotent** (every insert
  guarded by `NOT EXISTS` on the monitor name). Apply with
  `docker exec -i uptime-kuma sqlite3 /app/data/kuma.db < seed.sql` then `docker restart`.
- **Uptime Kuma v1 has NO REST API for monitor CRUD** — it is socket.io only. Monitors are either
  clicked in by hand or inserted into `kuma.db`. That is why this is a .sql file and not a script
  hitting an API.
- Public hostnames accept **2xx AND 3xx**: Overseerr answers 307 and Calibre-Web answers 302 (login
  redirects, not failures). Strict `200-299` would have alerted constantly — a false-alarm monitor
  gets muted and then misses the real outage.
- The *arr apps and qBittorrent are **TCP port** checks, so they need no API key and do not trip
  over login pages.
- AdGuard is monitored as a **`dns` type that actually resolves `github.com` through
  `192.168.68.56`**, not a port check — confirmed returning `140.82.113.3`. A port check would pass
  on a wedged-but-listening resolver, which is the failure that would take the whole LAN down.
- **Also still missing: a VPN kill-switch monitor.** Uptime Kuma cannot express "qBittorrent's exit
  IP is still PIA's". That needs a script comparing the two IPs feeding a **push** monitor. The
  qBittorrent port check only proves the process is alive, NOT that it is still tunnelled.

### ntfy alerting — and the silent-failure bug that made it useless (2026-08-05)

Channel: **ntfy.sh**, priority 4 (high: sounds, but does not override Do Not Disturb — a channel
that wakes you at 3am for a blip gets muted, and a muted channel is worse than none). Attached to
all 16 monitors and set as default so new monitors inherit it. Topic is a 24-hex-char random string
stored in `/volume1/docker/scripts/.creds` as `NTFY_TOPIC` and **deliberately not committed** —
ntfy.sh topics have no access control, so knowing the name is enough to read every alert.
`docker/uptime-kuma/seed-ntfy.sql.template` carries a `__NTFY_TOPIC__` placeholder instead.

**THE BUG — found only because the alerting was actually tested.** After wiring ntfy up, a
deliberate outage (stop `homepage`, watch it go DOWN) produced correct DOWN heartbeats and
**no notification at all**. The topic was empty. Uptime Kuma logged:

```
Cannot send notification to ntfy (phone)
400 {"code":40018,"error":"invalid request: actions invalid; parameter 'url' is required for action 'view'"}
```

- **Cause:** `/app/server/notification-providers/ntfy.js` attaches a "view" action button to every
  alert and fills its url from **`monitorJSON.url`** — the monitor's OWN `url` column, *not* the
  Primary Base URL setting. `port` and `dns` monitors never populate that column, so the url is
  null and **ntfy rejects the entire notification** with a 400.
- **Blast radius:** 10 of the 16 monitors were `port`/`dns` type — Sonarr, Radarr, Prowlarr, Bazarr,
  qBittorrent, Vaultwarden, Homepage, both LAN book services, and the AdGuard DNS check. Every one
  of them would have recorded outages correctly and **never told anyone**. Only the 6 HTTP monitors
  would have alerted.
- **A wrong first guess, recorded so it is not repeated:** setting `primaryBaseURL` looks like the
  fix and is not — the provider never reads it. Verified: the setting was applied, restarted, and
  the 400 continued unchanged.
- **Fix:** `docker/uptime-kuma/fix-ntfy-action-urls.sql` sets a `url` on every non-HTTP monitor,
  pointing at that service's own web UI (cosmetic for the check, which uses hostname+port — and it
  makes the button in the alert genuinely useful). Ends with a catch-all `UPDATE` so any future
  non-HTTP monitor cannot reintroduce this.
- **Verified after the fix by repeating the same deliberate outage:** 0 send errors, and the topic
  received `Homepage Down [Uptime-Kuma]` followed by `Homepage Up [Uptime-Kuma]`.
- **LESSON:** an alerting system that has never alerted is not installed, it is decorative. Both the
  channel *and* a real state transition have to be exercised — the direct `curl` test to ntfy.sh
  passed the whole time this was broken, because the topic was fine and Uptime Kuma was the problem.

### Vaultwarden is unusable over plain HTTP — needs a reverse proxy (2026-08-05)

The web vault at `http://192.168.68.56:8222` loads but refuses to work:
*"You are not using a secure context which is required for the Subtle Crypto API to work."*

- **This is not a misconfiguration, it is a browser rule.** Vaultwarden's own docs state the web
  vault uses web crypto APIs that browsers only expose over HTTPS, and this applies **even on a LAN**
  — network isolation does not exempt it. Binding it to a LAN IP over `http://` can never work.
  Upstream's recommended fix is a reverse proxy terminating TLS.
- The Bitwarden mobile apps and browser extensions also require HTTPS, so a browser flag override
  only ever fixes one desktop browser.
**RESOLVED same day — Caddy + Let's Encrypt, still LAN-only (`docker/caddy/`).**

`https://vault.patplex.net:8443` now serves a real Let's Encrypt certificate
(`CN=vault.patplex.net`, issuer Let's Encrypt YE1, valid 2026-08-06 → 2026-11-04) and returns 200.

- **Port 8443, not 443:** UGOS Pro's own web server already owns `0.0.0.0:80` and `0.0.0.0:443`.
  Those belong to the NAS OS. Costs nothing — DNS-01 needs no inbound port.
- **DNS-01 via Cloudflare** means a genuine trusted cert with **nothing exposed to the internet**.
  Verified: `vault.patplex.net` returns **NXDOMAIN from both 1.1.1.1 and 8.8.8.8**, and the
  Cloudflare zone holds **0 DNS records** for it — the ACME TXT record is created and cleaned up
  during validation. It resolves only via the AdGuard rewrite, on the LAN.
- Token is a **scoped** Zone:DNS:Edit token for patplex.net only, in a gitignored `.env` (chmod 600).
  Confirmed valid via Cloudflare's `/user/tokens/verify`; the account-level
  `/user/tokens/permission_groups` call fails, which is the expected proof it is scoped rather than
  a Global API Key.
- **CRLF TRAP:** writing the `.env` from PowerShell stores `CF_API_TOKEN=<token>\r`. The carriage
  return is invisible in every normal check and Cloudflare then rejects the token with an
  authentication error that says nothing about line endings. `od -c` the file, or pipe through
  `tr -d '\r'` on the NAS side. Applies to ANY secret written to the NAS from PowerShell.
- `DOMAIN` in the Vaultwarden compose **must** be the https URL clients use
  (`https://vault.patplex.net:8443`), not the raw LAN address — Vaultwarden derives links and
  WebAuthn/2FA origins from it, and a mismatch breaks 2FA registration.
- **Uptime Kuma needed `extra_hosts`** for `vault.patplex.net`: it only exists as an AdGuard
  rewrite, and Docker's embedded DNS does not consult AdGuard, so the container got NXDOMAIN and the
  monitor would have false-alarmed permanently. Pinned via `extra_hosts` rather than setting
  `dns: 192.168.68.56` on the container — this box MONITORS AdGuard, so making Uptime Kuma depend on
  AdGuard for resolution would fail every monitor at once during an AdGuard outage and bury the one
  alert that identifies the cause.
- Added monitor **"Vaultwarden (HTTPS)"** with `expiry_notification` on, so a silently
  non-renewing certificate raises an alert rather than a browser error in 90 days.
- Reusable: any other LAN service needing TLS is now three lines in the Caddyfile plus an AdGuard
  rewrite. `scripts/add-adguard-rewrite.sh` automates the DNS half.

### Follow-ups blocked on account creation (2026-08-05)

Three items are ready but need Pat to create an account first — Claude does not create accounts or
handle passwords, consistent with the PIA rule at the top of this file.

1. **Uptime Kuma** — `user` table is empty. Create the admin account at `http://192.168.68.56:3001`,
   then the monitors can be added. Note v1 has **no REST API for monitor CRUD** (socket.io only), so
   monitors are either clicked in the UI or seeded into `kuma.db` directly.
   Monitors wanted: the 4 public hostnames, AdGuard DNS `192.168.68.56:53`, Plex 32400,
   Sonarr 8989, Radarr 7878, Prowlarr 9696, qBittorrent 8080, Bazarr 6767, and the VPN exit IP.
2. **Vaultwarden** — create the first account at `http://192.168.68.56:8222`, then
   `SIGNUPS_ALLOWED` must be flipped to `false` in `docker/vaultwarden/docker-compose.yml` and
   redeployed. Until then anyone on the LAN can register.
3. **Bazarr + OpenSubtitles.com** — currently on three no-account providers (podnapisi, tvsubtitles,
   yifysubtitles). OpenSubtitles.com has much better coverage. Free account at
   opensubtitles.com, then add the credentials in Bazarr under
   Settings → Providers → OpenSubtitles.com (they land in `config.yaml` under the
   `opensubtitlescom:` key). Pat enters these directly.

### Maintainerr "Leaving Soon" rule — audited, grace period raised, keep-label added (2026-08-09)
Pat reported it was flagging recently-added movies. **Audited the rule first — it was written
correctly.** Decoded from Maintainerr's own enums (`RulePossibility`, `RuleType` in
`/opt/app/server/dist/modules/rules/constants/rules.constants.js`) rather than guessing:

| # | sec | Condition |
|---|---|---|
| 18 | 0 | Radarr `fileSize` BIGGER 15359 (MB → 15 GB) |
| 19 | 0 | AND Plex `viewCount` EQUALS 0 |
| 20 | 1 | AND Plex `addDate` BEFORE 7776000s (added >90 days ago) |

Sections combine with AND — confirmed in `rule.comparator.service.js`: the operator on the FIRST
rule of a new section sets `sectionActionAnd = +operator === 0`. Rule 20's operator is "0" = AND.

Verified against the real library (607 movies): smallest item on the list was 15.30 GB (0 under
threshold, so the size unit is MB not bytes), and 5 large unwatched movies newer than 90 days were
correctly held back. **Nothing was broken — 90 days is just shorter than it feels.**

**Changes made** (DB edited directly at `/volume1/Config/Maintainerr/maintainerr.sqlite`, backed up
first; the API path is `PUT /api/rules` but the RulesDto is easy to get wrong):
- Rule 20: `7776000` → `15552000` (90 → **180 days**)
- **New rule 21**, section 1, AND: Plex `labels` (prop 24, TEXT_LIST) **NOT_CONTAINS** `keep`

Why `NOT_CONTAINS` is safe for the ~600 untagged movies: `doRuleAction` implements NOT_CONTAINS as
`!CONTAINS`, and CONTAINS is `val1?.includes(val2)` — an empty/absent label list yields false, so
`!false = true` and untagged movies stay eligible. Only an explicit `keep` label opts a movie out.
Both sides are lowercased in `doRuleAction`, so Plex normalising the tag to "Keep" still matches.

**Verified end-to-end:** labelled *The Dark Knight* `keep`, ran `POST /api/rules/execute` → 6 items
removed (the 5 movies aged 119–176 days, plus The Dark Knight). List went 67 → 61, newest remaining
item is 219 days old. Nothing was deleted: all 67 entries had been added to the collection that
morning, and `deleteAfterDays` is 30, so nothing was near the delete window.

**Tagging is done in Plex Web only** (not the mobile/TV apps): Movies library → hover a poster and
tick its checkbox → select others → Edit → Tags → Labels → type `keep`.

### "Shrink instead of delete" for large unwatched movies (2026-08-09)
Pat asked for oversized unwatched movies to be **replaced with smaller copies** rather than deleted.

**Why Maintainerr can't do this alone:** its only arrActions are delete/unmonitor variants. And
**Radarr will never downgrade** — every smaller release is rejected with
`Existing file meets cutoff`. Verified: 137 of 140 releases rejected for exactly that reason even
after switching the movie to a 1080p-only profile with `upgradeAllowed: true`. The old file must
come out *before* the grab. That constraint is the whole reason this needs a script.

**Built:**
- Radarr quality profile **`Compact 1080p` (id 8)** — WEB 1080p + Bluray-1080p, no Remux, no 2160p.
- Radarr **recycle bin enabled** → `/recycle` (`/volume1/Media/.recycle`), 14 day retention. Needed
  a new bind mount on the radarr service in `docker/media/docker-compose.yml`. Nothing is destroyed;
  deletes become moves on the same filesystem.
- `scripts/shrink-oversized-movies.py` — takes its work list from the Maintainerr collection (so the
  rule stays the single source of truth), searches, picks the **largest** candidate that fits the
  band, and only then removes the old file and pushes that exact release. Dry run by default.
- `scripts/restore-from-recycle.py` — reverses a run, selecting by regex on the original filename.

**Maintainerr `arrAction` changed 0 (DELETE) → 4 (DO_NOTHING).** The collection is now a work queue,
not an execution list. Once a replacement imports the movie drops under 15 GB and leaves the
collection on its own — self-correcting, no loop, no bookkeeping.

**The mistake, and the guard it produced.** The first run shrank 42 movies (~681 GB) — but **27 of
them were Dolby Vision / Atmos / TrueHD**, which is exactly what Pat had said months earlier he
wanted preserved for the LG C5. Size was carried through as the only constraint; format was not.
Pat caught it when Lawrence of Arabia (2160p AV1 HDR TrueHD 7.1+Atmos) went. All 27 were restored
from the recycle bin, put back on profile 7, and verified.
The script now **refuses to touch DV/Atmos/TrueHD**, checking Radarr's parsed `mediaInfo`
(`audioCodec`, `videoDynamicRangeType`) first and the filename second, because release names lie.

**Also learned:** cancelling a grab leaves the movie briefly monitored-and-fileless, and Radarr
immediately grabs a *fresh* copy at the restored profile. Any restore has to sweep the queue
afterwards or you get surprise 2160p re-downloads.

Two other gotchas worth keeping:
- Radarr auto-picked a **1.84 GB YIFY** rip first. The script now blocklists YIFY/YTS/MeGusta/TGx
  and enforces a floor, because "1080p" alone says nothing about bitrate.
- The global quality definitions cap Bluray-1080p at 60 MB/min (~7 GB for a 2h film), left over from
  the earlier "best quality, smallest file" tuning — so replacements land ~3-7 GB, not 6-15 GB.

Net after restores: 15 non-premium movies shrinking, ~200 GB reclaimed. Originals stay in
`/recycle` for 14 days.

### IPTV in Plex via Dispatcharr (2026-08-09)
Pat has a paid IPTV subscription and wanted the channels inside Plex, with recording.

**Plex has no native M3U/IPTV input** — Live TV & DVR only talks to HDHomeRun-style tuners
(https://support.plex.tv/articles/225877427-supported-dvr-tuners-and-antennas/). So a bridge is
required that ingests M3U/Xtream + XMLTV and impersonates an HDHomeRun.

Pat considered buying Emby as a fallback. Not needed: **Plex Pass here is lifetime and active**
(confirmed via `plex.tv/api/v2/user` → `plan: lifetime`, role `plexpass`), and the same bridge
serves Plex, Emby and Jellyfin identically — no lock-in either way.

**Chose Dispatcharr** (`ghcr.io/dispatcharr/dispatcharr:latest`, v0.28.2 released 2026-07-23,
actively developed) over **Threadfin**, whose last tagged release is v1.2.37 from **Sept 2024** —
unmaintained for ~2 years. Threadfin is far lighter (~50 MB vs ~1 GB), which mattered here; see
the memory note below.

`docker/dispatcharr/docker-compose.yml`, AIO mode (bundles its own Postgres + Redis), port 9191,
bind-mounted at `/volume1/Config/Dispatcharr` so `backup-configs.sh` picks it up for free.

**`mem_limit: 1500m` is load-bearing, not decorative.** This is an 8 GB box already running Plex,
the *arr stack and a VPN'd qBittorrent. Dispatcharr **idles at ~1.0 GiB** and free RAM dropped from
2.3 GB to ~1.5 GB just by starting it. Without the cap it can grow into whatever is free and
starve Plex mid-stream. If this box starts swapping under a live transcode, Dispatcharr is the
first thing to cut — swapping to Threadfin is the escape hatch.

**No `/dev/dri` passthrough.** Dispatcharr can transcode via VA-API but Plex already owns the Intel
GPU (`HardwareAcceleratedCodecs=1`, verified). One GPU consumer = one place to debug. Dispatcharr
proxies, Plex transcodes.

**LAN only — deliberately NOT on the Cloudflare tunnel.** Re-serving a provider's streams publicly
breaks their terms and turns this into a redistribution point. `iptv.home` added via
`add-adguard-rewrite.sh`.

Recordings target `/volume1/Media/LiveTV`, a **sibling** of Movies/TV — never inside them, or
Sonarr/Radarr and the Maintainerr size rule would treat recordings as library content.

**Provider credentials are entered in the Dispatcharr web UI only** and live in its own DB. They
never touch a compose file, an `.env`, or git.

Pre-flight checks that saved guesswork later: the provider domain is **not** caught by AdGuard's
733k rules, and is reachable from inside the container (401 at root = expected, wants auth).

Open: nothing prunes DVR recordings — the Maintainerr rule covers the Movies library only.

#### Channel curation, EPG and the Plex tuner shim (2026-08-09, same day)
Provider import landed **14,728 channels / 36,442 streams / 377 groups**. Far too many for Plex,
whose Live TV is built around a few hundred linear channels.

Inspecting the groups showed two very different things mixed together:
- **Real linear channels** — `US: ACC Network`, `UK: Sky Sports F1 UHD`, `US: AMC`.
- **Per-event placeholder slots** — `NCAAF 02 :` (literally empty), `ESPN+ 07: PEC Zwolle vs Ajax
  @ Aug 09 8:25AM`. Hundreds of these; they'd fill the guide with dead rows.
- **225 CBS / 219 FOX / 214 NBC local affiliates**, one per US market.

`scripts/dispatcharr-build-plex-profile.py` builds a `Plex` ChannelProfile = **1,180 channels**
from 20 groups (linear sports/news/entertainment/movies/4K + the MLB/NHL/NBA/NCAAF game feeds).
Everything else stays in Dispatcharr, just not exposed — widening it is a one-line edit.

**EPG needed manual linking.** Dispatcharr's `match_epg_channels` only does fuzzy name matching for
channels with NO tvg_id; it never links channels whose tvg_id already matches an EPG entry exactly
— which was 856 of 860 here. The source sat at "No channels mapped (6609 entries available)" and
programmes stayed at 0 forever. `scripts/dispatcharr-link-epg.py` links by tvg_id then refreshes:
**3,403 channels linked, 121,937 programmes**. Programme fetch only runs for mapped entries, so the
link must happen first.

**Plex needs an HDHomeRun at a URL ROOT.** Its grabber probes `/discover.json`, `/lineup.json`,
`/lineup_status.json`, `/device.xml` at `host:port` and **ignores any path** in the address given
(`Grabber: HDHomerun discovered 0 compatible devices`). Dispatcharr serves the filtered profile at
`/hdhr/Plex/` and only serves `device.xml` at the unfiltered `/hdhr/` root — so pointing Plex at it
directly yields either no device or all 14,728 channels. Fixed with a ~10 MB nginx shim
(`plex-tuner-shim.conf`, port **9192**) that maps the profile to a root and rewrites the advertised
BaseURL. Stream URLs in lineup.json are already absolute to :9191, so playback bypasses the shim.

**The Plex manual-add endpoint is `POST /media/grabbers/devices?uri=<ip:port>`** — not
`/media/grabbers/devices/discover`, which silently ignores `uri` and just re-runs broadcast
discovery. The device must then be referenced by its full uuid
(`device://tv.plex.grabbers.hdhomerun/<id>`), not `key="1"`. Tuner now registers `status="alive"`,
10 tuners.

**Unfinished:** creating the DVR itself (`POST /livetv/dvrs`) still returns *"The EPG provider does
not exist."* for every `lineup=` format tried. The param format is undocumented and guessing was
wasting time — note that `/tv.plex.providers.epg.xmltv` is NOT evidence of a provider id; that path
echoes `content="plugins"` for any string. Finish this in the Plex UI: Live TV & DVR → the tuner is
already listed → choose the XMLTV guide option and paste
`http://192.168.68.56:9191/output/epg/Plex`.

Also open: no local affiliates in the profile (needs Pat's market), and nothing prunes recordings.
Memory holding at ~1.0 GiB for Dispatcharr + 2 MB for the shim; 1.4 GB free on the box.

#### Plex DVR: created, but channel mapping is blocked (2026-08-09)
**Two earlier diagnoses in this session were wrong and are recorded here so they are not repeated.**
The tuner wizard's "There was a problem saving channel mappings" was NOT caused by channel count,
and NOT by URL length:
- Plex parsed a **21 KB** query URL without complaint (returns 404 for a missing device, not 400).
- The channelmap PUT returns **400 at every size** — 100 channels / 706 bytes fails identically to
  1,005 channels / 6.6 KB. Size is irrelevant.

So the ~1,180-channel figure was a red herring; the profile was needlessly cut to 253 sports-only
channels on a bad assumption, then restored to **1,005 English channels (997 with EPG)**.

**What the log actually revealed** — the real lineup format the Plex web client uses, which is
undocumented and was not guessable:
```
lineup://tv.plex.providers.epg.xmltv/<percent-encoded xmltv url>#<guide title>
```
With that, `POST /livetv/dvrs?device=<uuid>&lineup=<above>&language=eng` **succeeds** — DVR key=2
created, guide attached, `refreshedAt` set, and Plex now advertises a `Live TV & DVR` MediaProvider
(`tv.plex.providers.epg.xmltv:2`) with Guide/grid/search features.

Also learned: the manual tuner-add endpoint is `POST /media/grabbers/devices?uri=<ip:port>` — NOT
`/media/grabbers/devices/discover`, which silently ignores `uri` and just re-runs UDP broadcast
discovery. The device must be referenced by full uuid, not `key`. Device channels come back as
`<DeviceChannel identifier=...>`, not `<Channel>`.

**The one remaining blocker:** saving the channel map.
`GET /livetv/epg/channelmap?device=..&lineup=..` returns a perfect 1:1 match for all 1,005 channels
(`deviceIdentifier == lineupIdentifier`), but every attempt to persist it returns 400:
`PUT /media/grabbers/devices/1/channelmap` with `channelsEnabled`, with `channelMapping` pairs,
with both, with a form body, with a JSON body; and `/livetv/dvrs/2/channelmap` is 404.
Until it saves, `/tv.plex.providers.epg.xmltv:2/grid` is empty.

Pat's browser failed at the *same* call — but on the **CORS preflight** (`400 OPTIONS`), because
app.plex.tv is cross-origin to the local server. That points at the Plex **desktop app** (no
browser CORS) as the most promising way to finish the wizard.

**Unrelated real bug found and fixed along the way:** Plex's `TranscoderTempDirectory` was set to
the HOST path `/volume1/transcode`, which does not exist inside the container (the mount lands at
`/transcode`). Plex had logged `Error creating directory "/volume1/transcode": Permission denied`
10 times. Set to `/transcode`. This affected ALL transcoding, not just live TV — the project's
recurring host-vs-container path-alignment failure, again.

### Live TV pivot: Plex DVR abandoned, TiviMate chosen (2026-08-09)
Pat asked point-blank whether a better app than Plex exists for IPTV. Honest answer: yes, almost
anything. The Plex route died on a hard, unfixable fact: the channel map goes in ONE ~40KB-max
request URI (PUT replaces, chunking does not accumulate — 21 chunks of 50 left only the last 5
channels mapped), capping a tuner at ~520 channels. Two hidden tuners would have worked, but at
that point the complexity existed only to satisfy Plex.

**Decision trail (Pat pushed for evidence, correctly):**
- Jellyfin: best FREE option, native M3U — but its live-TV guide UX is widely called clunky; not
  "the best available".
- **Channels DVR ($8/mo)**: the r/cordcutters pick for a whole-home DVR server — comskip, central
  recordings, polished guide. Recommended first because Pat had earlier asked for record-to-NAS.
- **TiviMate ($20 lifetime)**: the r/IPTV pick for pure viewing — fastest guide/zapping, runs on
  the Fire Stick already on the C5. No whole-home DVR (device-local only).
Pat chose TiviMate; it also spares the RAM-strapped NAS (~1.4 GB free) another server. If
recording becomes a habit later, Channels DVR can be added without redoing anything.

**Sharing question, answered honestly:** the bottleneck is the provider account, not the app.
In-house: any number of TVs, limited by the plan's 4 concurrent connections (Dispatcharr
max_streams set to 4 to match). Plex-style sharing to friends' homes: no app does this —
Channels has no friend-sharing, Plex only shares DVR recordings, and exposing the playlist
publicly is redistribution that gets provider accounts banned. Friends buy their own sub.

**Built for TiviMate:** `scripts/dispatcharr-build-tv-profile.py` → profile `TV`:
**1,438 channels** (763 sports — every league/team/conference feed Pat listed, 569 English cable,
106 4K), **138 24h-loop channels dropped** (detected from EPG: ≤1 distinct title in 24h; no-EPG
channels are NOT loopers, game-slot feeds legitimately have thin guides), best-quality variant
per channel (4K > FHD > HD > SD, per Pat). 1,233 of 1,438 carry EPG; 26,330 programmes.
- playlist `http://192.168.68.56:9191/output/m3u/TV` (guide URL embedded via x-tvg-url)
- guide    `http://192.168.68.56:9191/output/epg/TV`
- **Stream verified end-to-end**: 55 MB of clean MPEG-TS in 25 s (~18 Mbit/s) from the Sky Sports
  Main Event UHD channel through Dispatcharr's proxy.

**Torn down:** Plex DVR (key 2) + grabber device deleted (200s, dvrs size=0), nginx shim container
+ conf removed from box and repo, stale Dispatcharr profiles (Plex/PlexA/PlexB) deleted. Plex is
back to movies/TV only, untouched. Dispatcharr stays as the curation/EPG layer.

**Pat-side (documented in chat):** sideload TiviMate on the Fire Stick via the Downloader app,
add the playlist URL, buy Premium via the TiviMate Companion phone app (~$20 lifetime).

### Plex Live TV — WORKING (2026-08-09, evening)
Pat pushed back on abandoning the server-run route, correctly: with the API decoded, Plex's cap
is livable if the lineup is curated to fit. Asked Pat what they actually watch instead of
guessing; built to the answers.

**The two hard numbers, both measured not assumed:**
- Plex's channelmap URI limit is **exactly 32 KB** (binary search: 469 ids → 200, 470 → 400).
- The map PUT **replaces** the whole map — my 21-chunk "merge" earlier left only the last chunk's
  5 channels live. One request or nothing. Profile budget set to 460.

**`PlexTop` profile (456 channels, 416 with EPG), Pat's priorities:**
locals 20 (Green Bay + Madison + Milwaukee + Minneapolis — every Packers path: WLUK/WMSN/WITI/
KMSP + the dedicated NFL GREEN BAY PACKERS feed, force-whitelisted out of the vetoed Backup
group) · linear sports 201 · NFL team feeds 39 · BIG10+ all 50 (Badgers priority) · NCAAF 25 ·
SEC+ 15 · **fights 41 (UFC Channel, Fight Pass, PPV group un-vetoed on request)** · sports-4K 43
· news 25 · movies 35. Cut to make room: the 60 "Sky Sports+" numbered event streams (the real
Sky Sports linear channels stay).

**Gotchas that cost time:** the 24h-looper filter ate the dedicated Packers feed (off-season
placeholder EPG looks like a loop) — game/event tiers are now looper-exempt. The shim was
rebuilt for the PlexTop profile (9192). Wire-up is scripted end to end and repeatable:
build profile → POST device → POST dvr → ONE channelmap PUT (indexed params) → reloadGuide.

**Verified:** 386 channels in the DVR lineup, guide grid 1,249 entries, UFC + Packers + locals
confirmed present, Dispatcharr at 569 MiB, box at 1.6 GB available. TiviMate remains the
better-UX option on a $40-60 Google TV stick later; the 1,438-channel `TV` profile still serves
/output/m3u/TV for it. Plex was NOT the wrong tool by accident — it is the wrong tool by design
for IPTV — but it now works within its limits, runs off the server, and needs no new hardware.

### TiviMate prep: wide `TV` profile rebuilt; Xiaomi stick inbound (2026-08-09, night)
Pat bought a **Xiaomi TV Stick 4K (2nd Gen)** — Google TV, so TiviMate installs from the Play
Store natively (the sideload objection only ever applied to Fire OS). Arrives 2026-08-10.

`TV` profile rebuilt to "all the English channels you can": **3,900 channels** (was 1,438) —
locals for all four Packers markets + whitelist Packers feed, 965 sports (now incl. UFC/fight
PPV, USA Soccer, Fubo, F1 TV), 2,806 cable/streaming-FAST (Amazon Prime, PlexTV, Pluto, itvX,
EN✦ originals), 108 4K. **224 single-show loop channels dropped** by the 24h rule; the *Events
slot-dump groups stay vetoed. Looper exemption now group-based (Teams/game/PPV groups), so the
Packers-feed class of bug can't recur. EPG: 61,311 programmes, 18 MB — generation fine, memory
stable (Dispatcharr 646 MiB).

**Both frontends now run in parallel off one Dispatcharr:** Plex keeps the curated 456-channel
`PlexTop` DVR (owner/household only — Plex never shows Live TV to friend accounts; recordings in
/volume1/Media/LiveTV can be shared as a library, which is the actual ceiling for friends), and
TiviMate gets the full 3,900 via /output/m3u/TV. Provider's 4 concurrent connections arbitrated
by Dispatcharr max_streams=4.

### EZTV indexer outage — self-inflicted, now fixed (2026-08-16)
EZTV had been failing since **Aug 4** and Prowlarr had it benched. The root cause was **our own
security hardening**: FlareSolverr was rebound to 127.0.0.1:8191 (it had been an unauthenticated
headless browser open to the LAN), but Prowlarr's FlareSolverr proxy entry still pointed at
`http://192.168.68.56:8191` → connection refused. EZTV is the only indexer that routes through
FlareSolverr (Cloudflare), so it alone died. Fix: proxy host → `http://127.0.0.1:8191` (Prowlarr
is host-network, localhost reaches it). All 5 indexers test green; live EZTV search returns 199
results; bench cleared.

**Wrong turn, recorded:** the error surfaced truncated ("Connection refused (192...") next to
boilerplate advice about DNS/IPv6, and the first diagnosis chased IPv6 — the Deco does hand out a
useless private-only fd9c:: prefix and eztvx.to's IPv6 is genuinely unreachable from this LAN, so
`DOTNET_SYSTEM_NET_DISABLEIPV6=1` was added to Prowlarr (kept: harmless and correct for this
network). But the *actual* failure was the proxy port. The lesson: read the untruncated error
before theorizing — the port number was the whole answer.

**Standing rule this creates: when a service is rebound to localhost for security, grep the other
services' configs for the old LAN-IP URL.** Sonarr/Radarr checked — no other references to :8191.
