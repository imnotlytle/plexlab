#!/usr/bin/env python3
"""Extract Pat's edited ratings out of the .ods so a rebuild never loses his work."""
import json

from odf import table, teletype, text
from odf.opendocument import load


def rows_of(t):
    """Yield each row as a flat list of strings, expanding repeat counts."""
    out = []
    for r in t.getElementsByType(table.TableRow):
        cells = []
        for c in r.getElementsByType(table.TableCell):
            rep = int(c.getAttribute("numbercolumnsrepeated") or 1)
            val = c.getAttribute("value")
            if val is None:
                ps = c.getElementsByType(text.P)
                val = "".join(teletype.extractText(p) for p in ps) if ps else ""
            cells.extend([val] * min(rep, 50))
        out.append(cells)
    return out


doc = load("/work/updated.ods")
sheets = {t.getAttribute("name"): rows_of(t)
          for t in doc.spreadsheet.getElementsByType(table.Table)}

edits = {"movies": {}, "tv": {}, "audiobooks": {}}


def grab(sheet, key_idx, rate_hdr, bucket, extra_key_idx=None):
    rows = sheets.get(sheet) or []
    if not rows:
        return
    hdr = rows[0]
    try:
        ri = next(i for i, h in enumerate(hdr) if rate_hdr.lower() in (h or "").lower())
    except StopIteration:
        print("  !! no rating column in", sheet, hdr[:6])
        return
    n = 0
    for r in rows[1:]:
        if len(r) <= key_idx or not r[key_idx]:
            continue
        title = r[key_idx].strip()
        second = (r[extra_key_idx].strip()
                  if extra_key_idx is not None and len(r) > extra_key_idx else "")
        val = r[ri] if len(r) > ri else ""
        if val not in ("", None):
            try:
                edits[bucket][(title.lower(), str(second).lower())] = float(val)
                n += 1
            except ValueError:
                pass
    print("  %-12s ratings found: %d" % (sheet, n))


grab("Movies", 0, "My rating", "movies", extra_key_idx=1)
grab("TV Shows", 0, "My rating", "tv", extra_key_idx=1)
grab("Audiobooks", 0, "My rating", "audiobooks", extra_key_idx=1)

json.dump({k: {"|".join(kk): v for kk, v in d.items()} for k, d in edits.items()},
          open("/work/edits.json", "w"))
print("saved /work/edits.json")
