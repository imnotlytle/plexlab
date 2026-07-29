#!/usr/bin/env python3
"""Apply correct covers from archive.org to Audiobookshelf items.

Needed because ABS's providers fail for these books:
  - Audible returns unrelated books for the Turtledove "Darkness" titles (it matches the
    phrase, not the author), which is how "Into the Darkness" ended up with the cover of
    "Lights Out - An Into Darkness Novel" by Navessa Allen.
  - openlibrary.org is refusing connections (their outage), so ABS's OpenLibrary provider
    returns nothing.
archive.org IS reachable and serves real cover art at /services/img/<identifier>.
"""
import json, urllib.request, sqlite3

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

# library title -> archive.org identifier (verified to return a real JPEG)
COVERS = {
    "Into the Darkness":     "intodarkness00turt",
    "Darkness Descending":   "darknessdescendi00harr",
    "Through the Darkness":  "throughdarkness0000turt",
    "Rules of the Darkness": "rulersofdarkness00turt",   # actual book is "Rulers of the Darkness"
    "Jaws of Darkness":      "jawsofdarknesswo00harr",
    "Out of the Darkness":   "outofdarkness00turt_0",
    "Days of Infamy":        "daysofinfamy0000turt",
}


def login():
    body = json.dumps({"username": CREDS["ABS_USER"], "password": CREDS["ABS_PASS"]}).encode()
    r = urllib.request.Request(BASE + "/login", data=body,
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["user"]["token"]


TOK = login()
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}

conn = sqlite3.connect(DB)
ids = {t: i for t, i in conn.execute(
    "select b.title, li.id from libraryItems li join books b on b.id=li.mediaId")}

for title, ident in COVERS.items():
    iid = ids.get(title)
    if not iid:
        print("  %-22s NOT IN LIBRARY" % title)
        continue
    url = "https://archive.org/services/img/%s" % ident
    try:
        body = json.dumps({"url": url}).encode()
        r = urllib.request.Request(BASE + "/api/items/%s/cover" % iid,
                                   data=body, method="POST", headers=H)
        urllib.request.urlopen(r, timeout=60)
        print("  %-22s OK  <- %s" % (title, ident))
    except Exception as e:
        print("  %-22s ERR %s" % (title, str(e)[:60]))
