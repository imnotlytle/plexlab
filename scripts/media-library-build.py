#!/usr/bin/env python3
"""Build the media-library workbook, merged with Pat's Letterboxd export.

Everything numeric is written as a real number and every date as a real date — Plex and ABS hand
back strings, and if those go in verbatim Excel/LibreOffice store them as text, which sorts
alphabetically ("10" before "9") and shows the leading-apostrophe marker.
"""
import csv
import json
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

DATEFMT = "yyyy-mm-dd"
# Static build date rather than TODAY(): TODAY() is volatile, so 600+ of them force a full
# recalculation on every edit and make the workbook feel sluggish to open and type in.
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")


def num(v):
    if v in (None, "", "N/A"):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else round(f, 2)


def dt(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


d = json.load(open("/work/library.json"))

# ---------- merge Letterboxd ----------
lb_rows = [r for r in csv.DictReader(open("/work/ratings.csv", encoding="utf-8-sig"))
           if r.get("Name")]


def norm(s):
    s = (s or "").lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"^(the|a|an) ", "", s).strip()


lb_by_key = {}
for r in lb_rows:
    lb_by_key.setdefault(norm(r["Name"]), []).append(r)

# Ratings Pat has typed into a previous copy of the workbook. These win over everything else —
# losing his manual work on a rebuild would be the worst possible failure here.
try:
    EDITS = json.load(open("/work/edits.json"))
except FileNotFoundError:
    EDITS = {"movies": {}, "tv": {}, "audiobooks": {}}


def edited(bucket, title, second=""):
    return EDITS.get(bucket, {}).get(f"{(title or '').lower()}|{str(second or '').lower()}")


matched = set()
for m in d["movies"]:
    cands = lb_by_key.get(norm(m["title"]), [])
    pick = next((c for c in cands if str(c.get("Year")) == str(m["year"])), None) or \
        (cands[0] if cands else None)
    if pick:
        matched.add(id(pick))
        m["lb_rating"] = num(pick.get("Rating"))
        m["lb_uri"] = pick.get("Letterboxd URI", "")
    else:
        m["lb_rating"], m["lb_uri"] = None, ""
    mine = edited("movies", m["title"], m["year"])
    m["seed"] = mine if mine is not None else (
        m["lb_rating"] if m["lb_rating"] is not None else num(m["my_rating"]))
    # A rating means he watched it — Plex's counter only knows what was played on THIS server,
    # so films seen in a cinema or before he owned them show viewCount 0 despite being rated.
    m["watched"] = "Yes" if (num(m["times"]) or 0) > 0 or m["seed"] not in (None, "") else "No"

not_owned = [r for r in lb_rows if id(r) not in matched]

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=11)
RATE_FILL = PatternFill("solid", fgColor="FFF2CC")
LB_FILL = PatternFill("solid", fgColor="E2EFDA")
GREEN = PatternFill("solid", fgColor="C6EFCE")
AMBER = PatternFill("solid", fgColor="FFEB9C")
GREY = Font(color="808080")
HALF = '"0.5,1,1.5,2,2.5,3,3.5,4,4.5,5"'

wb = Workbook()
wb.remove(wb.active)


def make(name, headers, widths, rows, rating_col=None, status_col=None, status_colors=None,
         date_cols=(), pct_cols=(), centre_cols=()):
    ws = wb.create_sheet(name)
    ws.append(headers)
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=i)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.row_dimensions[1].height = 30
    for r in rows:
        ws.append(r)

    last = ws.max_row
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last}"

    for row in range(2, last + 1):
        for col in date_cols:
            ws.cell(row=row, column=col).number_format = DATEFMT
        for col in pct_cols:
            ws.cell(row=row, column=col).number_format = "0%"
        for col in centre_cols:
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")

    if rating_col:
        rc = get_column_letter(rating_col)
        dv = DataValidation(type="list", formula1=HALF, allow_blank=True,
                            showErrorMessage=True, errorTitle="Half stars only",
                            error="Letterboxd uses 0.5 to 5 in half-star steps.")
        ws.add_data_validation(dv)
        dv.add(f"{rc}2:{rc}{last}")
        for row in range(2, last + 1):
            c = ws.cell(row=row, column=rating_col)
            c.fill = RATE_FILL
            c.alignment = Alignment(horizontal="center")
            c.number_format = "0.0"

    if status_col and status_colors:
        sc = get_column_letter(status_col)
        for value, fill in status_colors:
            ws.conditional_formatting.add(
                f"{sc}2:{sc}{last}",
                CellIsRule(operator="equal", formula=[f'"{value}"'], fill=fill))
    return ws


# ---------------- Movies ----------------
H = ["Title", "Year", "Watched?", "My rating (0.5-5)", "Already on Letterboxd",
     "Plex rating", "Times", "Last watched", "Critic", "Audience", "Runtime (min)", "Added"]
rows = [[m["title"], num(m["year"]), m["watched"], m["seed"], m["lb_rating"], num(m["my_rating"]),
         num(m["times"]), dt(m["last_watched"]), num(m["critic"]), num(m["audience"]),
         num(m["runtime_min"]), dt(m["added"])] for m in d["movies"]]
ws = make("Movies", H, [44, 7, 10, 16, 15, 11, 7, 13, 9, 11, 13, 12], rows,
          rating_col=4, status_col=3, status_colors=[("Yes", GREEN)],
          date_cols=(8, 12), centre_cols=(2, 3, 5, 6, 7, 9, 10, 11))
for row in range(2, ws.max_row + 1):
    ws.cell(row=row, column=5).fill = LB_FILL
    for col in (5, 6):
        ws.cell(row=row, column=col).number_format = "0.0"

# ---------------- TV ----------------
H = ["Title", "Year", "Status", "Seasons", "Episodes", "Watched", "% watched",
     "My rating (0.5-5)", "Last watched", "Added"]
rows = []
for s in d["tv"]:
    mine = edited("tv", s["title"], s["year"])
    rating = mine if mine is not None else num(s["my_rating"])
    status = s["status"]
    if rating not in (None, "") and status == "Not started":
        status = "Finished"      # same rule as movies: a rating means he has seen it
    rows.append([s["title"], num(s["year"]), status, num(s["seasons"]), num(s["episodes"]),
                 num(s["watched_eps"]), (s["pct"] / 100 if s["episodes"] else None),
                 rating, dt(s["last_watched"]), dt(s["added"])])
make("TV Shows", H, [40, 7, 13, 9, 10, 9, 11, 16, 13, 12], rows,
     rating_col=8, status_col=3, status_colors=[("Finished", GREEN), ("Watching", AMBER)],
     date_cols=(9, 10), pct_cols=(7,), centre_cols=(2, 3, 4, 5, 6))

# ---------------- Audiobooks ----------------
H = ["Title", "Author", "Series", "Status", "% listened", "Finished on",
     "My rating (0.5-5)", "Hours", "Narrator", "Published"]
rows = []
for b in d["audiobooks"]:
    rating = edited("audiobooks", b["title"], b["author"])
    status = b["status"]
    if rating not in (None, "") and status == "Not started":
        status = "Finished"
    rows.append([b["title"], b["author"], b["series"], status,
                 (b["pct"] / 100 if b["pct"] else None), dt(b["finished_on"]), rating,
                 num(b["hours"]), b["narrator"], num(b["published"])])
make("Audiobooks", H, [44, 24, 22, 13, 11, 12, 16, 8, 22, 10], rows,
     rating_col=7, status_col=4, status_colors=[("Finished", GREEN), ("Listening", AMBER)],
     date_cols=(6,), pct_cols=(5,), centre_cols=(4, 8, 10))

# ---------------- Letterboxd Import ----------------
# Letterboxd's own export columns. Rating must be numeric; Date must be plain yyyy-mm-dd text
# in the CSV, so TEXT() is used rather than a date cell.
H = ["Date", "Name", "Year", "Letterboxd URI", "Rating"]
ws = wb.create_sheet("Letterboxd Import")
ws.append(H)
for i, h in enumerate(H, 1):
    c = ws.cell(row=1, column=i)
    c.fill, c.font = HEAD_FILL, HEAD_FONT
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.column_dimensions[get_column_letter(i)].width = [12, 46, 8, 26, 9][i - 1]
for i, m in enumerate(d["movies"], start=2):
    ws.append([
        f'=IF(Movies!D{i}="","",IF(Movies!H{i}<>"",TEXT(Movies!H{i},"yyyy-mm-dd"),'
        f'"{BUILD_DATE}"))',
        f'=IF(Movies!D{i}="","",Movies!A{i})',
        f'=IF(Movies!D{i}="","",Movies!B{i})',
        m["lb_uri"],
        f'=IF(Movies!D{i}="","",Movies!D{i})',
    ])
ws.freeze_panes = "A2"
ws.auto_filter.ref = f"A1:E{ws.max_row}"

# ---------------- Rated but not owned ----------------
H = ["Name", "Year", "Rating", "Rated on", "Letterboxd URI"]
rows = [[r["Name"], num(r.get("Year")), num(r.get("Rating")), dt(r.get("Date")),
         r.get("Letterboxd URI", "")]
        for r in sorted(not_owned, key=lambda x: -float(x.get("Rating") or 0))]
make("Rated, Not Owned", H, [46, 8, 9, 12, 26], rows,
     date_cols=(4,), centre_cols=(2, 3))

# ---------------- Summary ----------------
ws = wb.create_sheet("Summary", 0)
mv, tv, ab = d["movies"], d["tv"], d["audiobooks"]
seeded = sum(1 for m in mv if m["seed"] is not None and m["seed"] != "")
ws.append(["My Media Library"])
ws["A1"].font = Font(bold=True, size=16, color="1F3864")
ws.append([])
for k, v in [
    ("MOVIES", None), ("In library", len(mv)),
    ("Watched (per Plex)", sum(1 for m in mv if m["watched"] == "Yes")),
    ("Rating already filled in", seeded),
    ("  ...from Letterboxd", sum(1 for m in mv if m["lb_rating"] is not None)),
    ("Still to rate", len(mv) - seeded), (None, None),
    ("TV SHOWS", None), ("In library", len(tv)),
    ("Finished", sum(1 for s in tv if s["status"] == "Finished")),
    ("Part-way through", sum(1 for s in tv if s["status"] == "Watching")),
    ("Not started", sum(1 for s in tv if s["status"] == "Not started")), (None, None),
    ("AUDIOBOOKS", None), ("In library", len(ab)),
    ("Finished", sum(1 for b in ab if b["status"] == "Finished")),
    ("In progress", sum(1 for b in ab if b["status"] == "Listening")),
    ("Not started", sum(1 for b in ab if b["status"] == "Not started")), (None, None),
    ("LETTERBOXD", None), ("Films in your export", len(lb_rows)),
    ("Matched to your library", len(lb_rows) - len(not_owned)),
    ("Rated but not owned", len(not_owned)),
]:
    ws.append([k, v])
    if v is None and k:
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="1F3864")
ws.append([])
for note in [
    "Ratings use Letterboxd's 0.5-5 half-star scale. Yellow cells have a dropdown.",
    "Green column = already on Letterboxd (reference). Yellow = the one you edit.",
    "Nothing here writes back to Plex or Letterboxd automatically.",
    "",
    "TO IMPORT INTO LETTERBOXD:",
    "1. Open the 'Letterboxd Import' tab.",
    "2. Filter the Name column and untick (Blanks).",
    "3. Copy the visible rows into a new blank spreadsheet.",
    "4. Save As CSV (UTF-8), then upload at letterboxd.com/import",
]:
    ws.append([note])
    ws.cell(row=ws.max_row, column=1).font = GREY
ws.column_dimensions["A"].width = 74
ws.column_dimensions["B"].width = 12

wb.save("/out/My Media Library.xlsx")
print("movies %d (%d pre-rated) | tv %d | audiobooks %d | not owned %d"
      % (len(mv), seeded, len(tv), len(ab), len(not_owned)))
