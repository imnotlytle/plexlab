#!/usr/bin/env python3
"""Pull Movies + TV from Plex and Audiobooks from Audiobookshelf into one JSON blob.

Watched/rated state comes from the OWNER's account (Plex viewCount/userRating, ABS mediaProgress),
which is what Pat actually wants reflected — not the other shared users'.
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

PLEX = "http://127.0.0.1:32400"
ABS = "http://127.0.0.1:13378"
TOK = open("/tmp/ptok").read().strip()


def plex(path):
    with urllib.request.urlopen(f"{PLEX}{path}{'&' if '?' in path else '?'}X-Plex-Token={TOK}",
                                timeout=180) as r:
        return ET.fromstring(r.read())


def ts(v):
    if not v:
        return ""
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def stars(v):
    """Plex stores user rating 0-10; Pat wants 1-5 stars."""
    if v in (None, "", "0"):
        return ""
    try:
        return round(float(v) / 2, 1)
    except Exception:
        return ""


out = {}

# ---------- MOVIES ----------
movies = []
for v in plex("/library/sections/1/all").findall(".//Video"):
    vc = int(v.get("viewCount") or 0)
    movies.append({
        "title": v.get("title"),
        "year": v.get("year") or "",
        "watched": "Yes" if vc else "No",
        "times": vc,
        "last_watched": ts(v.get("lastViewedAt")),
        "my_rating": stars(v.get("userRating")),
        "rated_on": ts(v.get("lastRatedAt")),
        "critic": v.get("rating") or "",
        "audience": v.get("audienceRating") or "",
        "runtime_min": int(int(v.get("duration") or 0) / 60000) or "",
        "added": ts(v.get("addedAt")),
    })
movies.sort(key=lambda m: (m["title"] or "").lower())
out["movies"] = movies

# ---------- TV ----------
shows = []
for d in plex("/library/sections/2/all").findall(".//Directory"):
    leaves = int(d.get("leafCount") or 0)
    seen = int(d.get("viewedLeafCount") or 0)
    if leaves and seen >= leaves:
        status = "Finished"
    elif seen:
        status = "Watching"
    else:
        status = "Not started"
    shows.append({
        "title": d.get("title"),
        "year": d.get("year") or "",
        "status": status,
        "episodes": leaves,
        "watched_eps": seen,
        "pct": (round(100 * seen / leaves) if leaves else 0),
        "my_rating": stars(d.get("userRating")),
        "rated_on": ts(d.get("lastRatedAt")),
        "last_watched": ts(d.get("lastViewedAt")),
        "seasons": d.get("childCount") or "",
        "added": ts(d.get("addedAt")),
    })
shows.sort(key=lambda s: (s["title"] or "").lower())
out["tv"] = shows

# ---------- AUDIOBOOKS (Audiobookshelf) ----------
creds = {}
for line in open("/volume1/docker/scripts/.creds"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        creds[k.strip()] = v.strip()

req = urllib.request.Request(ABS + "/login",
                             data=json.dumps({"username": creds["ABS_USER"],
                                              "password": creds["ABS_PASS"]}).encode(),
                             headers={"Content-Type": "application/json"})
login = json.loads(urllib.request.urlopen(req, timeout=60).read())
atok = login["user"]["token"]
H = {"Authorization": "Bearer " + atok}

# progress is per-user and lives on /api/me
me = json.loads(urllib.request.urlopen(
    urllib.request.Request(ABS + "/api/me", headers=H), timeout=60).read())
prog = {}
for p in me.get("mediaProgress", []):
    prog[p.get("libraryItemId")] = p

libs = json.loads(urllib.request.urlopen(
    urllib.request.Request(ABS + "/api/libraries", headers=H), timeout=60).read())
books = []
for lib in libs.get("libraries", []):
    items = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{ABS}/api/libraries/{lib['id']}/items?limit=1000",
                               headers=H), timeout=180).read())
    for it in items.get("results", []):
        md = (it.get("media", {}) or {}).get("metadata", {}) or {}
        p = prog.get(it.get("id"), {})
        pct = round(100 * float(p.get("progress") or 0))
        if p.get("isFinished"):
            status = "Finished"
        elif pct > 0:
            status = "Listening"
        else:
            status = "Not started"
        dur = (it.get("media", {}) or {}).get("duration") or 0
        books.append({
            "title": md.get("title") or "",
            "author": md.get("authorName") or "",
            "series": (md.get("seriesName") or ""),
            "status": status,
            "pct": pct,
            "finished_on": (datetime.fromtimestamp(p["finishedAt"] / 1000, tz=timezone.utc)
                            .strftime("%Y-%m-%d") if p.get("finishedAt") else ""),
            "hours": round(float(dur) / 3600, 1) if dur else "",
            "narrator": md.get("narratorName") or "",
            "published": md.get("publishedYear") or "",
        })
books.sort(key=lambda b: (b["author"].lower(), b["title"].lower()))
out["audiobooks"] = books

json.dump(out, open("/tmp/library.json", "w"))
print("movies:", len(movies), "| tv:", len(shows), "| audiobooks:", len(books))
print("  movies watched:", sum(1 for m in movies if m["watched"] == "Yes"),
      "| rated:", sum(1 for m in movies if m["my_rating"] != ""))
print("  tv finished:", sum(1 for s in shows if s["status"] == "Finished"),
      "| watching:", sum(1 for s in shows if s["status"] == "Watching"),
      "| rated:", sum(1 for s in shows if s["my_rating"] != ""))
print("  books finished:", sum(1 for b in books if b["status"] == "Finished"),
      "| listening:", sum(1 for b in books if b["status"] == "Listening"))
