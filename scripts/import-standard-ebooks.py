#!/usr/bin/env python3
"""Bulk-import the Standard Ebooks catalogue into Calibre-Web Automated.

Standard Ebooks = public-domain classics, professionally typeset and proofread. Free and
legal to redistribute. This is the best-quality source for a "classics" library.

Notes learned the hard way:
  * The /downloads/*.epub URL returns an HTML interstitial ("Your Download Has Started!").
    You must append ?source=download to get the actual file.
  * The OPDS feed (/feeds/opds/all) is 401 - patron-only. The public /ebooks listing is not.
  * A browser User-Agent is required.

Files land in the CWA ingest folder, which auto-imports them into the library.
Polite: one request at a time with a delay.
"""
import os, re, time, urllib.request, sys

OUT = "/volume1/Media/Books/ingest"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
DELAY = float(os.environ.get("SE_DELAY", "1.0"))
BASE = "https://standardebooks.org"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0     # 0 = all


def get(url, timeout=60):
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(r, timeout=timeout).read()


def list_books():
    """Walk the paginated public listing; return unique /ebooks/author/title paths."""
    seen, page = [], 1
    while True:
        try:
            html = get("%s/ebooks?page=%d&per-page=48" % (BASE, page), 40).decode("utf-8", "ignore")
        except Exception as e:
            print("  page %d failed: %s" % (page, str(e)[:60]))
            break
        found = re.findall(r'/ebooks/([a-z0-9._-]+)/([a-z0-9._-]+)"', html)
        found = [(a, t) for a, t in found if t not in ("downloads",)]
        fresh = [p for p in dict.fromkeys(found) if p not in seen]
        if not fresh:
            break
        seen += fresh
        print("  page %d: +%d (total %d)" % (page, len(fresh), len(seen)))
        page += 1
        time.sleep(DELAY)
        if LIMIT and len(seen) >= LIMIT:
            break
    return seen[:LIMIT] if LIMIT else seen


os.makedirs(OUT, exist_ok=True)
books = list_books()
print("\nfound %d books; downloading to %s\n" % (len(books), OUT))

ok = skip = fail = 0
for i, (author, title) in enumerate(books, 1):
    fname = "%s_%s.epub" % (author, title)
    dest = os.path.join(OUT, fname)
    if os.path.exists(dest) and os.path.getsize(dest) > 20000:
        skip += 1
        continue
    url = "%s/ebooks/%s/%s/downloads/%s_%s.epub?source=download" % (BASE, author, title, author, title)
    try:
        data = get(url, 90)
        if data[:2] != b"PK":          # EPUB is a zip; anything else is an error page
            fail += 1
            print("  [%d/%d] %s -> not an epub" % (i, len(books), title[:40]))
            continue
        with open(dest, "wb") as f:
            f.write(data)
        ok += 1
        if ok % 25 == 0:
            print("  [%d/%d] %d downloaded" % (i, len(books), ok))
    except Exception as e:
        fail += 1
        print("  [%d/%d] %s -> %s" % (i, len(books), title[:40], str(e)[:50]))
    time.sleep(DELAY)

print("\ndone: %d downloaded, %d already present, %d failed" % (ok, skip, fail))
