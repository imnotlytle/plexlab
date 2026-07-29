#!/usr/bin/env python3
"""Audit audiobook folders for playback-ORDER problems (v2).

Audiobookshelf orders tracks by embedded TRACK tag when present, and falls back to
filename sort otherwise. So severity depends on BOTH:

  CRITICAL - filename sort is wrong AND track tags are missing/unusable
             -> the book WILL play out of order.
  WARNING  - filename sort is wrong but track tags are good
             -> fine in Audiobookshelf, may misorder in dumb players / after a re-tag.
  INFO     - duplicate track numbers (genuinely ambiguous).

v1 wrongly flagged "gaps" per-folder; multi-part books legitimately number tracks
continuously across part folders (Book 1 = 2..9, Book 2 = 10..20, ...). Gap detection is
therefore done per BOOK (top-level author/title), not per subfolder.
"""
import os, re, subprocess, json, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/volume1/Media/Audio/Regular"
AUDIO = (".mp3", ".m4a", ".m4b", ".flac", ".ogg")


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def probe(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_entries", "format_tags=track:chapter=id", path],
            capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out or "{}")
        raw = d.get("format", {}).get("tags", {}) or {}
        trk = raw.get("track") or raw.get("TRACK") or raw.get("Track")
        num = None
        if trk:
            m = re.match(r"\s*(\d+)", str(trk))
            if m:
                num = int(m.group(1))
        return num, len(d.get("chapters", []))
    except Exception:
        return None, 0


def book_dirs(root):
    """A 'book' = <root>/<Author>/<Title>; collect all audio under it, recursively."""
    books = {}
    for author in sorted(os.listdir(root)):
        apath = os.path.join(root, author)
        if not os.path.isdir(apath):
            continue
        for title in sorted(os.listdir(apath)):
            tpath = os.path.join(apath, title)
            if not os.path.isdir(tpath):
                continue
            files = []
            for dp, _dn, fn in os.walk(tpath):
                files += [os.path.join(dp, f) for f in fn if f.lower().endswith(AUDIO)]
            if files:
                books["%s/%s" % (author, title)] = files
    return books


def main():
    books = book_dirs(ROOT)
    print("Auditing %d books...\n" % len(books))
    crit, warn, info = [], [], []

    for name, paths in sorted(books.items()):
        if len(paths) < 2:
            continue
        # order as a naive player sees it (full relative path, lexicographic)
        lex = sorted(paths)
        nat = sorted(paths, key=natkey)
        name_order_wrong = lex != nat

        with ThreadPoolExecutor(max_workers=12) as ex:
            res = list(ex.map(probe, nat))
        tracks = [r[0] for r in res]
        have = [t for t in tracks if t is not None]

        tags_ok = False
        if len(have) == len(tracks) and have:
            ascending = have == sorted(have)
            no_dupes = len(set(have)) == len(have)
            tags_ok = ascending and no_dupes
            if not no_dupes:
                d = sorted({t for t in have if have.count(t) > 1})
                info.append((name, "duplicate track numbers %s (%d files)" % (d[:6], len(paths))))
            elif not ascending:
                info.append((name, "track tags disagree with filename order (%d files)" % len(paths)))

        if name_order_wrong and not tags_ok:
            missing = len(tracks) - len(have)
            why = "no track tags" if missing == len(tracks) else (
                  "%d/%d files missing track tags" % (missing, len(tracks)) if missing else "track tags unusable")
            crit.append((name, "filename sort is wrong AND %s (%d files)" % (why, len(paths))))
        elif name_order_wrong:
            warn.append((name, "filenames sort wrong (tags save it) (%d files)" % len(paths)))

    def dump(title, rows):
        print("%s: %d" % (title, len(rows)))
        for n, m in rows:
            print("   - %-58s %s" % (n[:58], m))
        print()

    dump("CRITICAL (will play out of order)", crit)
    dump("WARNING (ok in Audiobookshelf, fragile elsewhere)", warn)
    dump("INFO (ambiguous numbering)", info)


if __name__ == "__main__":
    main()
