"""Build the 'PlexTop' profile: Pat's picked <=500 channels for Plex Live TV on the LG C5.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

Plex's tuner cap is a hard one-request ~40KB channel map (~500 channels; the PUT replaces the
whole map, chunking does not accumulate — PLAN.md 2026-08-09). This profile is built to Pat's
stated priorities, asked explicitly rather than guessed:

  1. LOCALS  — Green Bay + Madison + Milwaukee + Minneapolis (FOX/NBC/CBS/CW/PBS).
               Packers games are the non-negotiable; they air on FOX, and all three WI FOX
               affiliates plus the dedicated Packers team feed are here.
  2. LINEAR SPORTS — ESPN/FS1/league networks/RSNs, US+UK+CA (Sky/TNT cover the soccer mains).
  3. NFL TEAM FEEDS — all 39 (football is the priority; includes NFL GREEN BAY PACKERS).
  4. NCAAF game slots + SEC+/ACC and BIG10+ conference overflows — "all of NCAA".
  5. 4K — SPORTS 4K only (~40); the nature/travel/concert 4K filler is skipped.
  6. NEWS — Pat watches news live.
  7. MOVIE CHANNELS — HBO/Showtime/Starz-style linear, with whatever room remains.

Deliberately ABSENT (Pat: "I dont need every single game on dedicated channels that are dead
90% of the year"): the MLB/NHL/NBA/MLS/EPL/LaLiga per-game slot groups and the MLB/NBA/NHL
per-team groups. Those sports keep their league networks and RSNs via tier 2. Entertainment
cable (A&E/Discovery/etc.) is out too — "almost never tv shows". The full 1,438-channel 'TV'
profile still exists for any M3U player.
"""
import re
from datetime import timedelta

from django.utils import timezone

from apps.channels.models import Channel, ChannelGroup, ChannelProfile, ChannelProfileMembership
from apps.epg.models import ProgramData

PROFILE = "PlexTop"
BUDGET = 460   # Plex's channelmap URI limit is exactly 32KB (measured by binary search:
               # 469 of our ids fit, 470 gets 400). 460 leaves margin for longer ids.

LOCAL_MARKET = re.compile(r"(Madison|Milwaukee|Green Bay|Minneapolis)", re.I)
SPORT_4K = re.compile(r"(sport|espn|nfl|nba|mlb|nhl|btn|big ?ten|sec|acc|tnt|dazn|golf|racing|"
                      r"f1|fight|boxing|ufc|ppv|soccer|football|fubo|tsn|sportsnet)", re.I)

# (tier, group prefixes, cap or None), in priority order per Pat:
#   - Big Ten / Wisconsin Badgers first among NCAA; a modest selection of other conferences
#   - UFC + fight pay-per-view matters; Matchroom (snooker/pool) does not
#   - the real conference networks (BTN, SEC Network, ACC Network) live in the linear tier,
#     so the capped slot groups here are game-day overflow only
#   - "UK | Sky Sports+" (60 numbered event streams) was cut to make room — the Sky Sports
#     Main Event/PL/Football linear channels stay, which is the soccer "main feeds" ask
TIERS = [
    ("locals", ["USA | Local CBS", "USA | Local FOX", "USA | Local NBC",
                "USA | Local CW", "USA | Local PBS"], None),
    ("linear", ["USA | Sports", "UK | Sky Sports", "UK | TNT Sports", "UK | Sports",
                "CA | Sports", "CA | Sportsnet"], None),
    ("nfl",    ["USA | NFL Teams"], None),
    ("big10",  ["USA | BIG10"], None),          # all of it — Badgers priority
    ("ncaaf",  ["USA | NCAAF"], 25),
    ("conf",   ["USA | SEC+"], 15),             # the "selection of other conferences"
    ("fights", ["Live Pay-Per View", "Live | UFC"], None),
    ("4k",     ["4K / UHD"], None),
    ("news",   ["USA | News"], 25),
    ("movies", ["USA | Movies"], None),
]

# Force-include regardless of group vetoes. The dedicated Packers feed lives in
# "USA | NFL Teams Backup" — a group otherwise excluded as duplicate slots — and Packers
# coverage is Pat's stated non-negotiable.
WHITELIST = re.compile(r"^NFL GREEN BAY PACKERS$", re.I)
# Game/event feeds show placeholder EPG off-season, which the 24h-loop rule misreads as a
# looper — it silently dropped the dedicated NFL GREEN BAY PACKERS feed once already.
LOOPER_EXEMPT = {"nfl", "big10", "ncaaf", "conf", "fights"}
# "Sky Sports+" veto kills only the 60-slot event group; startswith("UK | Sky Sports") would
# otherwise pull it in alongside the real Sky Sports channels.
VETO_GROUP = ["Backup", "ESPN+", "NEXT PRO", "Sky Sports+", "Matchroom"]

NON_ENGLISH = re.compile(r"^(?!US|USA|UK|CA|EN)[A-Z]{2}\s*[:|]")
QUALITY = re.compile(r"\s*\b(UHD|4K|FHD|HD|SD|HEVC|H265|1080p?|720p?|"
                     r"\(5\.1 \+ Stereo\)|5\.1|Stereo|\(Events? Only\))\b\s*", re.I)
PREFIX = re.compile(r"^(US|USA|UK|CA|EN)\s*[:|]\s*", re.I)


def rank(name):
    """Highest quality wins (Pat: keep 4K over SD)."""
    low = name.lower()
    if "4k" in low or "uhd" in low:
        return 0
    if "fhd" in low:
        return 1
    if re.search(r"\bhd\b", low):
        return 2
    if re.search(r"\bsd\b", low):
        return 4
    return 3


def base_name(name):
    return re.sub(r"\s+", " ", QUALITY.sub(" ", PREFIX.sub("", name))).strip(" -|:").lower()


def groups_for(prefixes):
    return [g for g in ChannelGroup.objects.all()
            if any(g.name.startswith(p) for p in prefixes)
            and not any(v.lower() in g.name.lower() for v in VETO_GROUP)]


now = timezone.now()
titles_by_epg = {}
for epg_id, title in (ProgramData.objects
                      .filter(start_time__lt=now + timedelta(hours=24), end_time__gt=now)
                      .values_list("epg_id", "title")):
    titles_by_epg.setdefault(epg_id, set()).add(title)


def is_looper(ch):
    if not ch.epg_data_id:
        return False
    t = titles_by_epg.get(ch.epg_data_id)
    return t is not None and len(t) <= 1


selected = {}
for c in Channel.objects.all():
    if WHITELIST.match(c.name):
        selected["wl::" + c.name.lower()] = c
print("whitelisted: %d" % len(selected))

for tier, prefixes, cap in TIERS:
    room = BUDGET - len(selected)
    if cap is not None:
        room = min(room, cap)
    if room <= 0:
        print("%-7s SKIPPED - budget spent" % tier)
        continue
    pool = []
    for c in Channel.objects.filter(channel_group__in=groups_for(prefixes)):
        if tier == "locals":
            if not LOCAL_MARKET.search(c.name):
                continue
        elif tier == "4k":
            if not SPORT_4K.search(c.name):
                continue
        elif NON_ENGLISH.match(c.name):
            continue
        if tier not in LOOPER_EXEMPT and is_looper(c):
            continue
        k = ("4k::" + c.name.lower()) if tier == "4k" else base_name(c.name)
        if k in selected:
            continue
        pool.append((rank(c.name), c.name, k, c))
    pool.sort(key=lambda t: (t[0], t[1]))
    taken = pool[:room]
    for _, _, k, c in taken:
        selected[k] = c
    print("%-7s +%-4d (total %d)" % (tier, len(taken), len(selected)))

keep_ids = {c.id for c in selected.values()}
print("TOTAL: %d (budget %d)" % (len(keep_ids), BUDGET))
assert len(keep_ids) <= BUDGET

profile, _ = ChannelProfile.objects.get_or_create(name=PROFILE)
have = set(ChannelProfileMembership.objects
           .filter(channel_profile=profile).values_list("channel_id", flat=True))
missing = [ChannelProfileMembership(channel_profile=profile, channel_id=cid,
                                    enabled=(cid in keep_ids))
           for cid in Channel.objects.values_list("id", flat=True) if cid not in have]
if missing:
    ChannelProfileMembership.objects.bulk_create(missing, batch_size=2000)
on = ChannelProfileMembership.objects.filter(channel_profile=profile,
                                             channel_id__in=keep_ids).update(enabled=True)
ChannelProfileMembership.objects.filter(channel_profile=profile)\
                                .exclude(channel_id__in=keep_ids).update(enabled=False)
epg = Channel.objects.filter(id__in=keep_ids, epg_data__isnull=False).count()
print("profile '%s': %d enabled (%d with EPG)" % (PROFILE, on, epg))

print("\nPackers coverage check:")
for c in Channel.objects.filter(id__in=keep_ids):
    if re.search(r"(Packers|WLUK|WMSN|WITI|KMSP)", c.name, re.I):
        print("   ", c.name[:60])
