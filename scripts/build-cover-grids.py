#!/usr/bin/env python3
"""Build cover contact-grids with EXACT title mapping for visual verification.

Uses explicit ffmpeg -i inputs + xstack. Do NOT use the image2 sequence reader
(-start_number with %03d) — it silently skips frames, which made an earlier audit's
index mapping wrong by 5 positions.

Writes grid_NN.jpg plus grid_NN.txt listing exactly which titles are in which cell.
"""
import sqlite3, os, json, shutil, sys, subprocess

DB = "/volume1/Config/AudioBookShelf/absdatabase.sqlite"
OUT = "/volume1/docker/_covercheck/grids"
COLS, ROWS = 4, 3
PER = COLS * ROWS
W, H = 240, 360
START = int(sys.argv[1]) if len(sys.argv) > 1 else 1   # 1-based index into sorted titles

conn = sqlite3.connect(DB)
rows = sorted(
    [(t, cp) for t, cp in conn.execute(
        "select b.title,b.coverPath from libraryItems li join books b on b.id=li.mediaId "
        "where li.isMissing=0") if cp],
    key=lambda x: x[0].lower())

shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)

items = []
for t, cp in rows:
    p = cp.replace("/metadata", "/volume1/Config/AudioBookShelf-metadata", 1) if cp.startswith("/metadata") else cp
    if os.path.exists(p):
        items.append((t, p))

print("total covers: %d" % len(items))
items = items[START - 1:]

gnum = 0
for i in range(0, len(items), PER):
    batch = items[i:i + PER]
    gnum += 1
    tmp = os.path.join(OUT, "_t%d" % gnum)
    os.makedirs(tmp, exist_ok=True)
    scaled = []
    for j, (t, p) in enumerate(batch):
        d = os.path.join(tmp, "%02d.jpg" % j)
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-i", p,
                        "-vf", "scale=%d:%d,setsar=1" % (W, H), d], check=False)
        if os.path.exists(d):
            scaled.append(d)
    n = len(scaled)
    if n == 0:
        continue
    layout = "|".join("%d_%d" % ((k % COLS) * W, (k // COLS) * H) for k in range(n))
    fc = ";".join("[%d:v]null[v%d]" % (k, k) for k in range(n)) + ";" + \
         "".join("[v%d]" % k for k in range(n)) + \
         "xstack=inputs=%d:layout=%s[o]" % (n, layout)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for s in scaled:
        cmd += ["-i", s]
    cmd += ["-filter_complex", fc, "-map", "[o]", "-frames:v", "1",
            os.path.join(OUT, "grid_%02d.jpg" % gnum)]
    subprocess.run(cmd, check=False)
    with open(os.path.join(OUT, "grid_%02d.txt" % gnum), "w", encoding="utf-8") as f:
        for k, (t, _) in enumerate(batch[:n]):
            f.write("r%dc%d  %s\n" % (k // COLS + 1, k % COLS + 1, t))
    shutil.rmtree(tmp, ignore_errors=True)
    print("grid_%02d.jpg : %s .. %s" % (gnum, batch[0][0][:26], batch[n - 1][0][:26]))
