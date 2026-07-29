#!/usr/bin/env python3
"""Round 2 cover fixes, found by visually auditing every cover in the library.

Each entry: library title -> (search title, author). Tries Audible first (exact
title+author match only), then archive.org (which is reachable and has real scans).
Never applies a fuzzy match - a wrong cover is worse than the current one.
"""
import json, urllib.request, urllib.parse, sqlite3

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

FIX = {
    "Rage":                                      ("Rage", "Richard Bachman"),
    "Rita Hayworth and the Shawshank Redemption": ("Rita Hayworth and Shawshank Redemption", "Stephen King"),
    "Storm of the Century":                      ("Storm of the Century", "Stephen King"),
    "The Art of War":                            ("The Art of War", "Sun Tzu"),
    "The Breathing Method":                      ("The Breathing Method", "Stephen King"),
    "The Dark Tower":                            ("The Dark Tower VII", "Stephen King"),
    "The Shining":                               ("The Shining", "Stephen King"),
}


def login():
    body = json.dumps({"username": CREDS["ABS_USER"], "password": CREDS["ABS_PASS"]}).encode()
    r = urllib.request.Request(BASE + "/login", data=body,
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["user"]["token"]


TOK = login()
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}


def audible(title, author):
    q = urllib.parse.urlencode({"title": title, "author": author, "provider": "audible"})
    try:
        res = json.loads(urllib.request.urlopen(
            urllib.request.Request(BASE + "/api/search/books?" + q, headers=H), timeout=30).read())
    except Exception:
        return None
    last = author.split()[-1].lower()
    for m in res if isinstance(res, list) else []:
        au = m.get("author")
        au = ", ".join(au) if isinstance(au, list) else (au or "")
        mt = (m.get("title") or "").strip().lower()
        if m.get("cover") and last in au.lower() and (mt == title.lower() or title.lower() in mt):
            return m["cover"]
    return None


def archive(title, author):
    q = "title:(%s) AND creator:(%s)" % (title, author.split()[-1])
    u = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(
        {"q": q, "fl[]": "identifier", "rows": 3, "output": "json"})
    try:
        d = json.loads(urllib.request.urlopen(u, timeout=25).read())
        for doc in d["response"]["docs"]:
            ident = doc["identifier"]
            img = "https://archive.org/services/img/%s" % ident
            r = urllib.request.urlopen(img, timeout=20)
            if len(r.read()) > 3000:      # skip 1x1 placeholders
                return img
    except Exception:
        pass
    return None


conn = sqlite3.connect(DB)
ids = {t: i for t, i in conn.execute(
    "select b.title, li.id from libraryItems li join books b on b.id=li.mediaId")}

for lib_title, (stitle, author) in FIX.items():
    iid = ids.get(lib_title)
    if not iid:
        print("  %-42s NOT IN LIBRARY" % lib_title)
        continue
    url = audible(stitle, author)
    src = "audible"
    if not url:
        url = archive(stitle, author)
        src = "archive.org"
    if not url:
        print("  %-42s no confident match - LEFT AS-IS" % lib_title)
        continue
    try:
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/items/%s/cover" % iid,
            data=json.dumps({"url": url}).encode(), method="POST", headers=H), timeout=60)
        print("  %-42s FIXED via %s" % (lib_title, src))
    except Exception as e:
        print("  %-42s ERR %s" % (lib_title, str(e)[:40]))
