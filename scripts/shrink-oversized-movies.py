#!/usr/bin/env python3
"""Replace oversized, long-unwatched movies with good 1080p copies instead of deleting them.

The work list comes from the Maintainerr "Large & Unwatched Movies" collection, which already
encodes: over 15 GB, never watched by anyone, added more than 180 days ago, and not labelled
`keep` in Plex. This script does not re-implement that logic - Maintainerr stays the source of
truth, so changing the rule there changes what this touches.

For each movie:
  1. Ask Radarr what releases actually exist (a real indexer search).
  2. Pick a replacement: allowed 1080p quality, enough seeders, inside the target size band,
     and not a known low-effort rip. Prefer the LARGEST that fits - the goal is a file that
     still looks good on a 4K TV, not the smallest possible download.
  3. ONLY once a replacement is chosen: remove the current file and push that exact release.
  4. If nothing qualifies, leave the movie completely alone and report it.

Nothing is deleted without a validated replacement already selected, and Radarr's recycle bin
(/recycle, 14 day retention) holds the original either way. Radarr will never downgrade on its
own - it rejects every smaller release with "Existing file meets cutoff" - which is why the old
file has to come out before the grab, and why this script exists at all.

Once the smaller file imports, the movie drops under 15 GB and Maintainerr removes it from the
collection by itself. No bookkeeping, no loop.

Usage:  shrink-oversized-movies.py [--apply] [--limit N] [--movie "Title"]
Default is a dry run that changes nothing.
"""
import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

RADARR = "http://127.0.0.1:7878"
PLEX = "http://127.0.0.1:32400"
RADARR_CFG = "/volume1/Config/Radarr/config.xml"
PLEX_PREFS = "/volume1/Config/Plex/Library/Application Support/Plex Media Server/Preferences.xml"
MAINTAINERR_DB = "/volume1/Config/Maintainerr/maintainerr.sqlite"
COLLECTION_ID = 1

COMPACT_PROFILE_ID = 8            # "Compact 1080p" - WEB 1080p + Bluray-1080p, no Remux, no 2160p
ALLOWED_QUALITIES = {"Bluray-1080p", "WEBDL-1080p", "WEBRip-1080p"}
MIN_SEEDERS = 10
MIN_GB = 3.0                      # below this, 1080p is visibly mushy on a big panel
MAX_GB = 14.0                     # must stay under Maintainerr's 15 GB rule or it never clears
MAX_FRACTION_OF_CURRENT = 0.60    # skip unless the replacement is a real saving

# Groups that hit the size target by throwing away bitrate. Cheap to download, bad on a 65" OLED.
BAD_RELEASE = re.compile(r"\b(YIFY|YTS(\.\w+)?|MeGusta|TGx|RARBGx)\b", re.I)

# NEVER shrink these. Dolby Vision and Atmos/TrueHD do not exist at 1080p in any meaningful form,
# so "shrinking" such a file silently throws the format away - which is exactly what went wrong on
# the first run (27 of 42 movies were DV/Atmos and had to be restored from the recycle bin).
# Checked against Radarr's parsed mediaInfo first, filename second, because release names lie.
PREMIUM_NAME = re.compile(r"\b(DV|DoVi|Dolby.?Vision|Atmos|TrueHD)\b", re.I)


def is_premium(movie_file):
    """True if this file carries Dolby Vision or an object-audio track worth protecting."""
    mi = movie_file.get("mediaInfo") or {}
    audio = (mi.get("audioCodec") or "").lower()
    hdr = (mi.get("videoDynamicRangeType") or "").lower()
    if "atmos" in audio or "truehd" in audio:
        return True
    if "dv" in hdr.split() or "dolby vision" in hdr:
        return True
    return bool(PREMIUM_NAME.search(movie_file.get("relativePath", "")))


def radarr_key():
    return ET.parse(RADARR_CFG).getroot().find("ApiKey").text


def plex_token():
    with open(PLEX_PREFS, encoding="utf-8") as f:
        m = re.search(r'PlexOnlineToken="([^"]+)"', f.read())
    return m.group(1) if m else None


def api(method, path, key, body=None, timeout=180):
    url = RADARR + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"X-Api-Key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def collection_tmdb_ids(token):
    """Plex rating keys in the Maintainerr collection -> TMDB ids (exact, not title matching)."""
    con = sqlite3.connect(MAINTAINERR_DB)
    keys = [r[0] for r in con.execute(
        "select plexId from collection_media where collectionId=?", (COLLECTION_ID,))]
    con.close()
    out = {}
    for rk in keys:
        try:
            url = f"{PLEX}/library/metadata/{rk}?includeGuids=1&X-Plex-Token={token}"
            with urllib.request.urlopen(url, timeout=30) as r:
                root = ET.fromstring(r.read())
        except Exception:
            continue
        video = root.find(".//Video")
        if video is None:
            continue
        for g in video.findall("Guid"):
            gid = g.get("id") or ""
            if gid.startswith("tmdb://"):
                out[int(gid.split("//")[1])] = video.get("title")
                break
    return out


def pick_release(releases, current_gb):
    """Best replacement, or (None, reason). Prefers the largest file that still fits the band."""
    cands = []
    seen_quality = False
    for r in releases:
        q = (r.get("quality") or {}).get("quality", {}).get("name")
        if q not in ALLOWED_QUALITIES:
            continue
        seen_quality = True
        title = r.get("title", "")
        gb = r.get("size", 0) / 1024 ** 3
        seeders = r.get("seeders") or 0
        # "Existing file meets cutoff" is expected - the old file is still on disk right now.
        blocking = [str(x) for x in (r.get("rejections") or [])
                    if not str(x).startswith("Existing file meets cutoff")]
        if blocking or BAD_RELEASE.search(title) or seeders < MIN_SEEDERS:
            continue
        if not (MIN_GB <= gb <= MAX_GB):
            continue
        if gb > current_gb * MAX_FRACTION_OF_CURRENT:
            continue
        cands.append((gb, seeders, r))
    if not cands:
        if not seen_quality:
            return None, "no 1080p releases at all"
        return None, "no candidate met size/seeder/quality bar"
    cands.sort(key=lambda c: (-c[0], -c[1]))       # biggest that fits, tie-break on health
    return cands[0], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually make changes")
    ap.add_argument("--limit", type=int, default=0, help="stop after N movies")
    ap.add_argument("--movie", help="only this title (substring match)")
    args = ap.parse_args()

    key, token = radarr_key(), plex_token()
    if not token:
        sys.exit("could not read Plex token")

    wanted = collection_tmdb_ids(token)
    movies = {m["tmdbId"]: m for m in api("GET", "/api/v3/movie", key)}

    todo = []
    for tmdb, title in wanted.items():
        m = movies.get(tmdb)
        if not m or not m.get("hasFile"):
            continue
        todo.append(m)
    todo.sort(key=lambda m: -m["movieFile"]["size"])
    if args.movie:
        todo = [m for m in todo if args.movie.lower() in m["title"].lower()]
    if args.limit:
        todo = todo[:args.limit]

    mode = "APPLY" if args.apply else "DRY RUN (nothing will change)"
    print(f"=== shrink-oversized-movies | {mode} | {len(todo)} movies ===\n")

    saved = 0.0
    done = skipped = 0
    for m in todo:
        cur_gb = m["movieFile"]["size"] / 1024 ** 3
        name = f'{m["title"]} ({m.get("year","?")})'
        if is_premium(m["movieFile"]):
            print(f"  KEEP  {name:<45} {cur_gb:5.1f} GB -> Dolby Vision / Atmos, protected")
            skipped += 1
            continue
        try:
            rel = api("GET", f"/api/v3/release?movieId={m['id']}", key, timeout=300)
        except Exception as e:
            print(f"  SKIP  {name:<45} search failed: {str(e)[:40]}")
            skipped += 1
            continue

        pick, reason = pick_release(rel, cur_gb)
        if not pick:
            print(f"  KEEP  {name:<45} {cur_gb:5.1f} GB -> {reason}")
            skipped += 1
            continue

        gb, seeders, r = pick
        q = r["quality"]["quality"]["name"]
        print(f"  SHRINK {name:<44} {cur_gb:5.1f} GB -> {gb:5.2f} GB  {q}  ({seeders} seeds)")
        print(f"         {r.get('title','')[:88]}")
        saved += cur_gb - gb

        if args.apply:
            try:
                m["qualityProfileId"] = COMPACT_PROFILE_ID
                m["monitored"] = True
                api("PUT", f"/api/v3/movie/{m['id']}", key, m)
                api("DELETE", f"/api/v3/moviefile/{m['movieFile']['id']}", key)
                api("POST", "/api/v3/release", key,
                    {"guid": r["guid"], "indexerId": r["indexerId"]})
                done += 1
                time.sleep(2)
            except Exception as e:
                print(f"         !! FAILED: {str(e)[:70]}  (original is in /recycle)")
                skipped += 1

    print(f"\n  {done} queued, {skipped} left alone, ~{saved:.0f} GB to reclaim")
    if not args.apply:
        print("  re-run with --apply to execute")


if __name__ == "__main__":
    main()
