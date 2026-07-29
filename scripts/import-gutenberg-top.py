#!/usr/bin/env python3
"""Import Project Gutenberg's most-downloaded books into Calibre-Web Automated.

Curation rationale: Gutenberg has ~61k English texts, but the overwhelming majority are
obscure (19th-c pamphlets, government reports). Their bookshelves are broad categories, not
quality lists. Download COUNT is the best available proxy for "the classics people read",
so this pulls the published top-1000.

Downloads come from a Gutenberg MIRROR (gutenberg.pglaf.org), not www.gutenberg.org —
their policy asks robots to use mirrors for bulk fetching.

Files land in the CWA ingest folder and are auto-imported.
"""
import os, re, time, urllib.request, urllib.error, sys

OUT = "/volume1/Media/Books/ingest"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MIRROR = "https://gutenberg.pglaf.org"
DELAY = float(os.environ.get("PG_DELAY", "1.0"))
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def get(url, timeout=60, tries=4):
    delay = 4
    for a in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and a < tries - 1:
                time.sleep(delay); delay *= 2; continue
            raise
    raise RuntimeError("retries exhausted")


def top_ids():
    """Top-1000 by downloads, plus the top-100 lists, de-duplicated in rank order."""
    ids = []
    for u in ("https://www.gutenberg.org/browse/scores/top1000.php",
              "https://www.gutenberg.org/browse/scores/top"):
        try:
            html = get(u, 40).decode("utf-8", "ignore")
        except Exception as e:
            print("  %s failed: %s" % (u, str(e)[:50])); continue
        for m in re.findall(r"/ebooks/(\d+)", html):
            if m not in ids:
                ids.append(m)
    return ids


os.makedirs(OUT, exist_ok=True)
ids = top_ids()
if LIMIT:
    ids = ids[:LIMIT]
print("top-download ids collected: %d\n" % len(ids))

ok = skip = fail = 0
for i, bid in enumerate(ids, 1):
    dest = os.path.join(OUT, "pg%s.epub" % bid)
    if os.path.exists(dest) and os.path.getsize(dest) > 10000:
        skip += 1; continue
    data = None
    # mirrors keep a few naming variants; try the plain text-only epub first
    for name in ("pg%s.epub" % bid, "pg%s-images.epub" % bid, "pg%s-images-3.epub" % bid):
        try:
            d = get("%s/cache/epub/%s/%s" % (MIRROR, bid, name), 60)
            if d[:2] == b"PK":
                data = d; break
        except Exception:
            continue
    if data is None:
        fail += 1
        print("  [%d/%d] pg%s -> no epub found" % (i, len(ids), bid))
    else:
        with open(dest, "wb") as f:
            f.write(data)
        ok += 1
        if ok % 50 == 0:
            print("  [%d/%d] %d downloaded" % (i, len(ids), ok))
    time.sleep(DELAY)

print("\ndone: %d downloaded, %d already present, %d failed" % (ok, skip, fail))
