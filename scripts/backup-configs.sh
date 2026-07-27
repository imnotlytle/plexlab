#!/bin/sh
# Snapshot the NAS app configs + docker stack definitions to a local rotating archive.
# Captures the precious, hard-to-recreate state (app databases, compose files, .env's);
# excludes re-downloadable caches (Plex metadata, *arr poster art) and the recycle bin.
#
# NOTE: the archive contains .env secrets (PIA login, Cloudflare token). It stays on
# /volume1 — if you ever copy it offsite/cloud, treat it as sensitive.
#
# LIMITATION: this is a LOCAL backup (same pool). It protects against config corruption,
# bad upgrades, and fat-finger deletes — NOT against total drive/pool loss. Add an
# offsite/external copy of /volume1/backups/config for real disaster protection.

DEST=/volume1/docker/_backups/config
KEEP=14
mkdir -p "$DEST"
OUT="$DEST/nas-config-$(date +%Y%m%d-%H%M).tar.gz"

tar czf "$OUT" --warning=no-file-changed \
  --exclude='*/MediaCover' \
  --exclude='*/Cache' --exclude='*/cache' \
  --exclude='*/Metadata' \
  --exclude='*/logs' --exclude='*/Logs' \
  --exclude='Config/Plex/Library/Application Support/Plex Media Server/Media' \
  --exclude='Config/Plex/Library/Application Support/Plex Media Server/Metadata' \
  --exclude='Config/Plex/Library/Application Support/Plex Media Server/Cache' \
  --exclude='Config/#recycle' \
  --exclude='Config/Firefox' \
  --exclude='docker/_backups' \
  -C /volume1 Config docker
rc=$?
if [ "$rc" -gt 1 ]; then echo "tar FAILED rc=$rc" >&2; exit "$rc"; fi

# keep only the newest $KEEP archives
ls -1t "$DEST"/nas-config-*.tar.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f

echo "backup OK: $OUT ($(du -h "$OUT" | cut -f1)); retained $(ls -1 "$DEST"/nas-config-*.tar.gz | wc -l) snapshot(s)"
