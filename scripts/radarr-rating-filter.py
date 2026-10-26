#!/usr/bin/env python3
"""Gate Radarr's auto-added new releases on IMDb and Rotten Tomatoes scores.

Radarr's TMDb import lists can only filter on TMDb's own rating. Pat wants new releases only
when they clear BOTH bars: IMDb > 5.0 AND Rotten Tomatoes >= 50%. The lists therefore add
candidates UNMONITORED (nothing downloads), and this script decides:

  pass     -> monitor it and trigger a search (it downloads)
  fail     -> delete it (files too, if any) and add an import exclusion so no list re-adds it
  pending  -> leave it unmonitored until IMDb has a rating

Rules (Pat, 2026-10-25):
  - Only movies carrying the `auto-trending` tag are ever touched. That tag is applied by the
    import lists, and Radarr lists never re-tag a movie that was already in the library, so
    nothing Pat owned before the lists existed can match. Belt-and-braces: movies added before
    the lists were created are also skipped.
  - IMDb must exist and be > 5.0. RT must be >= 50 when present; if RT has no score yet, IMDb
    alone decides (small releases often never get an RT score).
  - Scores are re-checked every run, so a film whose RT later drops below 50 is removed.
  - A movie someone explicitly requested through Seerr is never deleted, whatever its score.

Usage: radarr-rating-filter.py [--apply]     (default is a dry run)
"""
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

RADARR = "http://127.0.0.1:7878/api/v3"
SEERR = "http://127.0.0.1:5055/api/v1"
RADARR_CFG = "/config/radarr.xml"
SEERR_CFG = "/config/seerr-settings.json"
TAG_LABEL = "auto-trending"
LISTS_CREATED = "2026-10-18"
IMDB_MIN = 5.0          # strictly greater than
RT_MIN = 50             # greater than or equal

APPLY = "--apply" in sys.argv
RK = ET.parse(RADARR_CFG).getroot().find("ApiKey").text


def radarr(method, path, body=None):
    req = urllib.request.Request(RADARR + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Api-Key": RK, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def seerr_requested_tmdb_ids():
    """tmdbIds anyone has explicitly requested — those are protected from deletion."""
    try:
        key = json.load(open(SEERR_CFG))["main"]["apiKey"]
    except Exception:
        return None                       # unknown -> caller refuses to delete anything
    ids, skip = set(), 0
    while True:
        req = urllib.request.Request(f"{SEERR}/request?take=100&skip={skip}&filter=all",
                                     headers={"X-Api-Key": key})
        d = json.loads(urllib.request.urlopen(req, timeout=60).read())
        for r in d.get("results", []):
            if r.get("type") == "movie":
                ids.add((r.get("media") or {}).get("tmdbId"))
        skip += 100
        if skip >= d.get("pageInfo", {}).get("results", 0):
            return ids


def verdict(m):
    r = m.get("ratings") or {}
    imdb = (r.get("imdb") or {}).get("value")
    rt = (r.get("rottenTomatoes") or {}).get("value")
    if rt is not None and rt < RT_MIN:
        return "fail", imdb, rt
    if imdb is None:
        return "pending", imdb, rt
    if imdb <= IMDB_MIN:
        return "fail", imdb, rt
    return "pass", imdb, rt


tags = {t["label"]: t["id"] for t in radarr("GET", "/tag")}
tag = tags.get(TAG_LABEL)
if tag is None:
    sys.exit(f"no '{TAG_LABEL}' tag in Radarr — nothing to do")

requested = seerr_requested_tmdb_ids()
queue = radarr("GET", "/queue?pageSize=500").get("records", [])
movies = [m for m in radarr("GET", "/movie")
          if tag in (m.get("tags") or []) and (m.get("added") or "")[:10] >= LISTS_CREATED]

print(f"{datetime.now():%Y-%m-%d %H:%M} | {'APPLY' if APPLY else 'DRY RUN'} | "
      f"{len(movies)} auto-trending movies | seerr protection: "
      f"{'on' if requested is not None else 'UNAVAILABLE - deletes disabled'}")

to_search = []
counts = {"pass": 0, "fail": 0, "pending": 0, "protected": 0}
for m in sorted(movies, key=lambda x: x["title"]):
    v, imdb, rt = verdict(m)
    label = f"{m['title'][:38]:<38} imdb={imdb!s:<4} rt={rt!s:<4}"

    if v == "fail":
        if requested is None or m.get("tmdbId") in requested:
            counts["protected"] += 1
            print(f"  KEEP    {label} fails, but {'requested in Seerr' if requested else 'Seerr unreachable'}")
            continue
        counts["fail"] += 1
        print(f"  DELETE  {label} {'(has file)' if m['hasFile'] else ''}")
        if APPLY:
            for q in queue:
                if q.get("movieId") == m["id"]:
                    radarr("DELETE", f"/queue/{q['id']}?removeFromClient=true&blocklist=false")
            radarr("DELETE", f"/movie/{m['id']}?deleteFiles=true&addImportExclusion=true")

    elif v == "pass":
        counts["pass"] += 1
        if not m["monitored"]:
            print(f"  MONITOR {label}")
            if APPLY:
                m["monitored"] = True
                radarr("PUT", f"/movie/{m['id']}", m)
                if not m["hasFile"]:
                    to_search.append(m["id"])

    else:
        counts["pending"] += 1
        if m["monitored"] and not m["hasFile"]:
            print(f"  HOLD    {label} no IMDb score yet - unmonitoring until rated")
            if APPLY:
                m["monitored"] = False
                radarr("PUT", f"/movie/{m['id']}", m)

if APPLY and to_search:
    radarr("POST", "/command", {"name": "MoviesSearch", "movieIds": to_search})

print(f"  -> pass {counts['pass']} | delete {counts['fail']} | pending {counts['pending']} | "
      f"protected {counts['protected']}" + ("" if APPLY else "  (dry run, nothing changed)"))
