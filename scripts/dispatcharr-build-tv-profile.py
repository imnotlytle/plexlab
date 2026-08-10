"""Build the 'TV' channel profile in Dispatcharr for TiviMate — Pat's full spec, no channel cap.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

TiviMate consumes this profile directly:
    playlist  http://192.168.68.56:9191/output/m3u/TV
    guide     http://192.168.68.56:9191/output/epg/TV

Unlike Plex (one-PUT ~520-channel tuner cap that killed the DVR route — see PLAN.md 2026-08-09),
TiviMate has no channel limit, so the whole spec fits one profile:

  - ALL sports: linear networks, every team feed (all NFL, all MLB, NBA, NHL), major-league and
    conference game slots (MLB/NHL/NBA/NCAAF/SEC+/BIG10/MLS), top soccer (EPL, La Liga, Ligue 1)
  - ALL 4K/UHD channels
  - ALL English cable (entertainment/news/movies/docs, US/UK/CA)
  - prefer the highest-quality copy of a channel (4K > FHD > HD > SD)
  - drop any channel showing one programme for 24h straight (FAST loops); channels with no EPG
    are NOT loopers — game-slot feeds legitimately have thin guides
"""
import re
from datetime import timedelta

from django.utils import timezone

from apps.channels.models import Channel, ChannelGroup, ChannelProfile, ChannelProfileMembership
from apps.epg.models import ProgramData

PROFILE = "TV"

SPORTS_PREFIX = [
    "USA | Sports", "UK | Sky Sports", "UK | TNT Sports", "UK | Sports",
    "CA | Sports", "CA | Sportsnet",
    "USA | NFL Teams", "USA | MLB Teams", "USA | NBA Teams", "USA | NHL Teams",
    "USA | MLB ", "USA | NHL ", "USA | NBA ", "USA | NCAAF",
    "USA | SEC+", "USA | BIG10", "USA | MLS ",
    "Live | English Premier League", "Live | La Liga", "Live | Ligue1",
    # fights matter (Pat): UFC + fight PPV. Matchroom (snooker/pool) stays out via veto.
    "Live Pay-Per View", "Live | UFC",
]
# Locals for Pat's markets — Packers coverage is the whole point (they air on FOX).
LOCAL_PREFIX = ["USA | Local CBS", "USA | Local FOX", "USA | Local NBC",
                "USA | Local CW", "USA | Local PBS"]
LOCAL_MARKET = re.compile(r"(Madison|Milwaukee|Green Bay|Minneapolis)", re.I)
# The dedicated Packers feed lives in the otherwise-vetoed "NFL Teams Backup" group.
WHITELIST = re.compile(r"^NFL GREEN BAY PACKERS$", re.I)
FOURK_PREFIX = ["4K / UHD"]
# "All the English channels you can" (Pat, for TiviMate — no channel cap there). The 24h-looper
# rule and the *Events-group veto are what keep this from becoming a junk drawer: single-show
# FAST loops get dropped automatically, dead per-event slot groups never enter.
CABLE_PREFIX = [
    "USA | Entertainment", "USA | News", "USA | Movies", "USA | Documentary",
    "UK | Entertainment", "UK | News", "UK | Movies", "UK | Documentary",
    "CA | Entertainment", "CA | Movies", "CA | Documentary", "CA | Kids",
    "USA | Amazon Prime", "USA | PlexTV", "USA | Pluto TV",
    "UK | Amazon Prime Channels", "CA | Amazon Prime Channels",
    "UK | itvX", "USA | ALLBLK", "USA | Peacock LIVE",
    "EN",                       # every EN-prefixed streaming-original group
]
EXTRA_SPORTS = ["USA | Soccer", "CA | Fubo", "Live | F1 TV"]
SPORTS_PREFIX += EXTRA_SPORTS
# "Sky Sports+" = 60 numbered event overflow streams; the real Sky Sports channels stay.
# "Event" kills the per-event slot dumps (Disney+/Dazn/Peacock/MAX/Prime Events) wholesale.
VETO_GROUP = ["Backup", "ESPN+", "NEXT PRO", "Sky Sports+", "Matchroom", "Event"]

NON_ENGLISH = re.compile(r"^(?!US|USA|UK|CA|EN)[A-Z]{2}\s*[:|]")
QUALITY = re.compile(r"\s*\b(UHD|4K|FHD|HD|SD|HEVC|H265|1080p?|720p?|"
                     r"\(5\.1 \+ Stereo\)|5\.1|Stereo|\(Events? Only\))\b\s*", re.I)
PREFIX = re.compile(r"^(US|USA|UK|CA|EN)\s*[:|]\s*", re.I)


def rank(name):
    """Highest quality wins: 4K/UHD > FHD > HD > unmarked > SD."""
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


# Game/event/team feeds show placeholder EPG off-season, which reads as a 24h loop — this
# silently dropped the dedicated Packers feed once. Never looper-drop these groups.
LOOPER_EXEMPT_GROUP = re.compile(
    r"(Teams|NCAAF|SEC\+|BIG10|MLB |NHL |NBA |MLS |Premier League|La Liga|Ligue1|"
    r"Pay-Per View|UFC)", re.I)


def is_looper(ch):
    if not ch.epg_data_id:
        return False
    if ch.channel_group and LOOPER_EXEMPT_GROUP.search(ch.channel_group.name):
        return False
    t = titles_by_epg.get(ch.epg_data_id)
    return t is not None and len(t) <= 1


selected = {}
loopers = []

# whitelist first: force-included regardless of group vetoes
for c in Channel.objects.all():
    if WHITELIST.match(c.name):
        selected["wl::" + c.name.lower()] = c
print("whitelisted: +%d" % len(selected))

# locals: only Pat's markets, from the per-market affiliate groups
n0 = len(selected)
for c in Channel.objects.filter(channel_group__in=groups_for(LOCAL_PREFIX)):
    if LOCAL_MARKET.search(c.name) and not is_looper(c):
        k = base_name(c.name)
        if k not in selected:
            selected[k] = c
print("locals: +%d" % (len(selected) - n0))

# sports + cable: English-only, dedupe variants keeping the best quality
for bucket, prefixes in (("sports", SPORTS_PREFIX), ("cable", CABLE_PREFIX)):
    n0 = len(selected)
    for c in Channel.objects.filter(channel_group__in=groups_for(prefixes)):
        if NON_ENGLISH.match(c.name):
            continue
        if is_looper(c):
            loopers.append(c.name)
            continue
        k = base_name(c.name)
        if k not in selected or rank(c.name) < rank(selected[k].name):
            selected[k] = c
    print("%s: +%d" % (bucket, len(selected) - n0))

# 4K: ALL of it (no English filter, no cross-variant dedupe), minus loopers only
n0 = len(selected)
for c in Channel.objects.filter(channel_group__in=groups_for(FOURK_PREFIX)):
    if is_looper(c):
        loopers.append(c.name)
        continue
    selected["4k::" + c.name.lower()] = c
print("4k: +%d" % (len(selected) - n0))

keep_ids = {c.id for c in selected.values()}
print("\nTOTAL: %d channels | loopers dropped: %d" % (len(keep_ids), len(loopers)))

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
