# nas-homelab

Configuration-as-code for a UGREEN DXP2800 running a media, book, and DNS stack for a household
and a handful of friends.

Every service is defined by a compose file in this repo, deployed to the NAS over SSH. Secrets live
only in gitignored `.env` files on the NAS itself and are never committed.

- **[PLAN.md](PLAN.md)** — the running log: every change, why it was made, and the gotchas found
  along the way. Read this before changing anything.
- **[notes/inventory.md](notes/inventory.md)** — original state of the box before any of this.

---

## Hardware

| | |
|---|---|
| **NAS** | UGREEN DXP2800, Intel N100 (4 core), 8 GB RAM, UGOS Pro (Debian-based) |
| **Storage** | 2 × 24 TB in RAID1 (mirror) + 2 × 4 TB NVMe RAID1 as LVM cache → 22 TB usable |
| **Network** | TP-Link Deco mesh (consumer — no VLANs), gigabit WAN |
| **Workstation** | Ryzen 7 7800X3D / 32 GB — used for anything the N100 is too slow for |

The N100 matters more than it looks: it is fast enough to serve media but too slow for heavy
transcoding or OpenVPN at line rate. Both facts drove real decisions below.

---

## Architecture

```
                          internet
                              │
                    Cloudflare Tunnel  (no inbound ports open on the router)
                              │
        ┌──────────────┬──────┴───────┬───────────────┐
   overseerr.        abs.          books.        shelfmark.
   patplex.net    patplex.net   patplex.net    patplex.net
        │              │              │               │
   ┌────┴──────────────┴──────────────┴───────────────┴────┐
   │                      UGREEN NAS                        │
   │                                                        │
   │  media:   Plex · Overseerr · Sonarr · Radarr           │
   │           Prowlarr · Tautulli · Maintainerr            │
   │                                                        │
   │  books:   Calibre-Web · Shelfmark · Audiobookshelf     │
   │                                                        │
   │  infra:   AdGuard Home (network DNS) · Diun            │
   │                                                        │
   │  ┌──────────────────────────────────────────────┐      │
   │  │ wireguard-pia  ← only internet exit          │      │
   │  │   └── qBittorrent (shares its netns)         │      │
   │  │       no VPN ⇒ no connectivity (kill-switch) │      │
   │  └──────────────────────────────────────────────┘      │
   └────────────────────────────────────────────────────────┘
```

**Nothing is port-forwarded.** All external access is via Cloudflare Tunnel, so the router has no
inbound holes. Four hostnames are published; everything else is LAN-only.

---

## Services

### Public (via Cloudflare Tunnel, all authenticated)

| Service | URL | Purpose |
|---|---|---|
| Overseerr | `overseerr.patplex.net` | Movie/TV requests for shared Plex users |
| Audiobookshelf | `abs.patplex.net` | Audiobook library, 148 books, ~2,100 hours |
| Calibre-Web | `books.patplex.net` | Ebook library + OPDS for e-readers |
| Shelfmark | `shelfmark.patplex.net` | Book search/acquire, feeds both libraries |

### LAN only

| Service | Port | Purpose |
|---|---|---|
| Plex | 32400 | Media server |
| qBittorrent | 8080 | Behind the PIA VPN kill-switch |
| Prowlarr | 9696 | Indexer manager |
| Sonarr / Radarr / Readarr | 8989 / 7878 / 8787 | TV / movies / books (Readarr is retired upstream) |
| AdGuard Home | 3000, DNS on 53 | Network-wide DNS + ad blocking |
| Tautulli | 8181 | Plex analytics |
| Maintainerr | 6246 | Rule-based library cleanup |
| Diun | — | Emails when container images have updates |
| FlareSolverr | 127.0.0.1:8191 | Cloudflare solver for indexers — **localhost only** |

Convenience hostnames via AdGuard (`plex.home`, `calibre.home`, `qbit.home`, `tautulli.home`, …)
all resolve to the NAS; append the port.

---

## Key design decisions

Full reasoning in [PLAN.md](PLAN.md); the load-bearing ones:

**qBittorrent runs inside the VPN container's network namespace.** Not alongside it — inside it.
`network_mode: service:wireguard-pia` means qBittorrent has no network path except the tunnel, so
if the VPN drops it loses all connectivity rather than falling back to the real WAN. Verified by
stopping the tunnel and confirming zero egress.

**PIA over WireGuard, not OpenVPN.** gluetun only supports PIA via OpenVPN, which is single-threaded
and CPU-bound — it capped at **14 Mbps at 55% CPU** on the N100. Switching to
`thrnz/docker-wireguard-pia` gave **127 Mbps at ~0% CPU**, a 9× improvement measured on the same
well-seeded torrent. Do not switch back.

**Path alignment is the recurring failure mode.** Every import bug in this project traced to a
download client and its consumer disagreeing about a container path. qBittorrent reports the path it
sees; the importer must see the *same* path. Check this first when something downloads but never
appears.

**Audiobooks are organised into folders, not renamed flat.** Audiobookshelf treats a folder as a
book, so a flat pile of MP3s is unusable. `FILE_ORGANIZATION_AUDIOBOOK=organize`.

**No VLAN isolation.** A consumer router can't do it, so isolation is container-level. The
high-value boundary (torrent traffic) is enforced by the VPN namespace instead. A VLAN-capable
router is the upgrade path.

---

## Operations

### Access

```bash
ssh -F secrets/ssh_config nas          # key auth; user is in the docker group
```

The NAS sshd has **no SFTP subsystem**, so `scp` fails. Copy files with:

```bash
ssh -F secrets/ssh_config nas 'cat > /remote/path' < localfile
```

### Deploying a change

1. Edit the compose file in `docker/<service>/` here
2. Copy it to the NAS with the `cat >` idiom above
3. `docker compose up -d` in that directory
4. Verify, then commit

### Scheduled jobs

| When | What |
|---|---|
| every 2 min | `shelfmark-auth-watch.sh` — restarts Shelfmark when Calibre-Web users change |
| every 5 min | `qbit-port-sync.sh` — keeps qBittorrent's port matched to PIA's forwarded port |
| daily 04:15 | `backup-configs.sh` — rotating config snapshots (keeps 14) |

Installed as root entries in `/etc/cron.d/` (the user crontab spool is root-only).

### Scripts

| Script | Does |
|---|---|
| `backup-configs.sh` | Snapshot `/volume1/Config` + `/volume1/docker`, excluding re-downloadable caches |
| `qbit-port-sync.sh` | Sync qBittorrent's listen port to PIA's forwarded port |
| `shelfmark-auth-watch.sh` | Auto-restart Shelfmark when the Calibre-Web user DB changes |
| `watch-audiobook-imports.sh` | Report whether finished torrents actually landed in the library |
| `Merge-Audiobooks.ps1` | Merge multi-file audiobooks into single chaptered `.m4b` (runs on the PC) |
| `audiobook-order-check.py` | Detect chapter-ordering problems (scrambled track tags, bad padding) |
| `build-cover-grids.py` | Build contact sheets for visually auditing cover art |
| `import-standard-ebooks.py` | Bulk-import the Standard Ebooks catalogue |
| `import-gutenberg-top.py` | Import Project Gutenberg's most-downloaded titles |

---

## Security posture

- **No inbound ports.** Cloudflare Tunnel only.
- **Four public hostnames**, all verified to reject unauthenticated API calls (401).
- **Torrent traffic cannot leave un-tunnelled** — enforced by network namespace, not configuration.
- **Secrets** in `.env` files at mode 600, gitignored. Re-check permissions after any redeploy —
  overwriting a file with `cat >` resets them.
- **Removed:** an orphaned Portainer agent holding a read-write Docker socket (root-equivalent,
  unused); LAN exposure of an unauthenticated headless browser (FlareSolverr).

Known gaps, deliberately: no VLAN isolation (consumer router), several LAN services have no auth,
and backups are same-pool only — **an offsite copy is the biggest remaining hole**.

---

## Gotchas worth knowing

Things that cost real debugging time here:

- **Renaming a library folder breaks Audiobookshelf** until you rescan — items go stale and
  streaming fails with an unhelpful error.
- **Shelfmark caches the Calibre-Web auth DB.** New users can't log in until it restarts (now
  automated).
- **ffmpeg's `%03d` image-sequence reader silently skips frames.** It made a cover audit's index
  mapping wrong by five positions. Use explicit `-i` inputs.
- **rsync filter order matters** — excludes must precede includes, or `--include` wins first.
- **PowerShell 5.1 turns a native exe's stderr into errors.** Never pass `-stats` or `2>&1` to
  ffmpeg from PowerShell; the script "fails" on success.
- **Audible metadata search ignores the author.** Turtledove's *Into the Darkness* got the cover of
  a romance novel with a similar title. Verify covers visually, not by trusting the matcher.
- **`.m4b` and `.mp3` contain digits.** Strip the extension before parsing a track number out of a
  filename, or every file scores the same.
