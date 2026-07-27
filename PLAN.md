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

- [ ] **Phase 0 — Access setup:** enable SSH, create this project, connect
- [ ] **Phase 1 — Inventory & cleanup:** audit current Plex + Docker, document the mess
- [ ] **Phase 2 — Media stack:** clean docker-compose for Plex + Overseerr
- [ ] **Phase 3 — VPN download stack:** gluetun (PIA) + qBittorrent with kill-switch
- [ ] **Phase 4 — Isolation & hardening:** separate networks, drop caps, minimal ports
- [ ] **Phase 5 — Backup & maintenance:** config backups + update strategy

## Decisions log

- 2026-07-27: Chose gluetun kill-switch pattern over router-level isolation (consumer router can't VLAN).
- 2026-07-27: qBittorrent on the NAS (not a separate Pi) — single place to manage; isolation via Docker networking.

## Open items / needs

- PIA credentials — user provides directly to config; Claude never handles them.
- NAS LAN IP + SSH username/port.
- Inventory of what's currently running (Phase 1).
