#!/usr/bin/env python3
"""Re-match Audiobookshelf covers that got attached to the WRONG book.

ABS's auto-matcher picks the FIRST provider result, which for ambiguous titles grabs a
completely different book (e.g. Turtledove's "Into the Darkness" got the cover of
"Lights Out - An Into Darkness Novel" by Navessa Allen).

This only applies a cover when the provider returns an EXACT title match, and it can
strip covers that are known-wrong when no correct one exists (better blank than misleading).
"""
import json, urllib.request, urllib.parse, sqlite3, sys

BASE = "http://localhost:13378"

def _creds(path="/volume1/docker/scripts/.creds"):
    """Read credentials from a gitignored file so this script is safe in a public repo."""
    d = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
    except FileNotFoundError:
        raise SystemExit("credentials file not found: " + path)
    return d


CREDS = _creds()
DB = "/volume1/Config/AudioBookShelf/absdatabase.sqlite"


def login():
    body = json.dumps({"username": CREDS["ABS_USER"], "password": CREDS["ABS_PASS"]}).encode()
    r = urllib.request.Request(BASE + "/login", data=body,
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["user"]["token"]


TOK = login()
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}


def search(title, author, provider="audible"):
    q = urllib.parse.urlencode({"title": title, "author": author, "provider": provider})
    r = urllib.request.Request(BASE + "/api/search/books?" + q, headers=H)
    try:
        return json.loads(urllib.request.urlopen(r, timeout=30).read())
    except Exception:
        return []


def set_cover(item_id, url):
    body = json.dumps({"url": url}).encode()
    r = urllib.request.Request(BASE + "/api/items/%s/cover" % item_id,
                               data=body, method="POST", headers=H)
    urllib.request.urlopen(r, timeout=60)


def clear_cover(item_id):
    r = urllib.request.Request(BASE + "/api/items/%s/cover" % item_id,
                               method="DELETE", headers=H)
    urllib.request.urlopen(r, timeout=30)


conn = sqlite3.connect(DB)
ids = {t: i for t, i in conn.execute(
    "select b.title, li.id from libraryItems li join books b on b.id=li.mediaId")}

# (library title, author to search with)
TARGETS = [
    ("Hyperion", "Dan Simmons"),
    ("Days of Infamy", "Harry Turtledove"),
    ("Apt Pupil", "Stephen King"),
    ("Into the Darkness", "Harry Turtledove"),
    ("Darkness Descending", "Harry Turtledove"),
    ("Through the Darkness", "Harry Turtledove"),
    ("Rules of the Darkness", "Harry Turtledove"),
    ("Out of the Darkness", "Harry Turtledove"),
    ("Jaws of Darkness", "Harry Turtledove"),
]

STRIP_IF_UNMATCHED = sys.argv[1:2] == ["--strip"]

for title, author in TARGETS:
    iid = ids.get(title)
    if not iid:
        print("  %-22s NOT IN LIBRARY" % title)
        continue
    hit = None
    for prov in ("audible", "google", "openlibrary"):
        res = search(title, author, prov)
        if not isinstance(res, list):
            continue
        for m in res:
            mt = (m.get("title") or "").strip().lower()
            au = m.get("author")
            au = ", ".join(au) if isinstance(au, list) else (au or "")
            # require BOTH an exact title match and the right author
            if mt == title.lower() and author.split()[-1].lower() in au.lower() and m.get("cover"):
                hit = (m, prov)
                break
        if hit:
            break
    if hit:
        m, prov = hit
        try:
            set_cover(iid, m["cover"])
            print("  %-22s FIXED via %s" % (title, prov))
        except Exception as e:
            print("  %-22s ERROR %s" % (title, str(e)[:50]))
    elif STRIP_IF_UNMATCHED:
        try:
            clear_cover(iid)
            print("  %-22s no correct cover found -> CLEARED wrong cover" % title)
        except Exception as e:
            print("  %-22s clear failed: %s" % (title, str(e)[:40]))
    else:
        print("  %-22s no correct cover found (left as-is)" % title)
