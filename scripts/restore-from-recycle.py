#!/usr/bin/env python3
"""Put originals back from Radarr's recycle bin, undoing a shrink.

Written to reverse the 2026-08-09 shrink run after it turned out to have swallowed Dolby Vision
and Atmos tracks. Selects by a regex against the ORIGINAL filename, so it can target just the
premium-audio/video copies rather than everything.

Per movie:
  1. Cancel and blocklist any in-flight replacement so it cannot import later.
  2. If a replacement already imported, remove it (that file goes to the recycle bin in turn).
  3. Move the original back into the movie folder.
  4. Put the movie back on its original quality profile and rescan.

Usage: restore-from-recycle.py [--apply] [--pattern REGEX] [--profile N]
Default is a dry run.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

RADARR = "http://127.0.0.1:7878"
RADARR_CFG = "/volume1/Config/Radarr/config.xml"
RECYCLE_HOST = "/volume1/Media/.recycle"
MOVIES_HOST = "/volume1/Media/Movies"

DEFAULT_PATTERN = r"\b(DV|DoVi|Dolby.?Vision|Atmos|TrueHD)\b"
VIDEO_EXT = (".mkv", ".mp4", ".m4v", ".avi")


def key():
    return ET.parse(RADARR_CFG).getroot().find("ApiKey").text


def api(method, path, k, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(RADARR + path, data=data, method=method,
                                 headers={"X-Api-Key": k, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--profile", type=int, default=7, help="quality profile to restore to")
    args = ap.parse_args()

    pat = re.compile(args.pattern, re.I)
    k = key()
    movies = api("GET", "/api/v3/movie", k)
    by_folder = {os.path.basename(m["path"].rstrip("/")): m for m in movies}
    queue = (api("GET", "/api/v3/queue?pageSize=200", k) or {}).get("records", [])

    targets = []
    for folder in sorted(os.listdir(RECYCLE_HOST)):
        src_dir = os.path.join(RECYCLE_HOST, folder)
        if not os.path.isdir(src_dir):
            continue
        vids = [f for f in os.listdir(src_dir)
                if f.lower().endswith(VIDEO_EXT) and pat.search(f)]
        if not vids:
            continue
        vids.sort(key=lambda f: os.path.getsize(os.path.join(src_dir, f)), reverse=True)
        m = by_folder.get(folder)
        if not m:
            print(f"  ?? {folder:<50} no matching Radarr movie - skipped")
            continue
        targets.append((folder, vids[0], m))

    mode = "APPLY" if args.apply else "DRY RUN (nothing will change)"
    print(f"=== restore-from-recycle | {mode} | {len(targets)} movies ===\n")

    restored = failed = 0
    for folder, fname, m in targets:
        src = os.path.join(RECYCLE_HOST, folder, fname)
        gb = os.path.getsize(src) / 1024 ** 3
        dest_dir = os.path.join(MOVIES_HOST, folder)
        qitems = [q for q in queue if q.get("movieId") == m["id"]]
        print(f"  {m['title'][:42]:<44} {gb:5.1f} GB  "
              f"{'[cancel ' + str(len(qitems)) + ' dl]' if qitems else ''}")
        if not args.apply:
            continue
        try:
            for q in qitems:
                api("DELETE", f"/api/v3/queue/{q['id']}?removeFromClient=true&blocklist=true", k)
            fresh = api("GET", f"/api/v3/movie/{m['id']}", k)
            if fresh.get("hasFile"):
                api("DELETE", f"/api/v3/moviefile/{fresh['movieFile']['id']}", k)
                time.sleep(1)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, os.path.join(dest_dir, fname))
            fresh["qualityProfileId"] = args.profile
            fresh["monitored"] = True
            api("PUT", f"/api/v3/movie/{m['id']}", k, fresh)
            api("POST", "/api/v3/command", k, {"name": "RescanMovie", "movieIds": [m["id"]]})
            leftover = os.path.join(RECYCLE_HOST, folder)
            if os.path.isdir(leftover) and not any(
                    f.lower().endswith(VIDEO_EXT) for f in os.listdir(leftover)):
                shutil.rmtree(leftover, ignore_errors=True)
            restored += 1
            time.sleep(1)
        except Exception as e:
            print(f"       !! FAILED: {str(e)[:80]}")
            failed += 1

    print(f"\n  {restored} restored, {failed} failed")
    if not args.apply:
        print("  re-run with --apply to execute")


if __name__ == "__main__":
    main()
