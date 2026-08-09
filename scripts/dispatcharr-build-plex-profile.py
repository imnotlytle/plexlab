"""Build the Plex channel selection in Dispatcharr to Pat's spec, split across two tuners.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

THE CONSTRAINT: Plex saves a tuner's entire channel map in ONE request URI, rejects URIs over
~40 KB (~70 bytes/channel), and the PUT replaces the whole map — chunking does not accumulate.
Hard cap ~520 channels per tuner. The spec below needs ~940+, so the selection is split across
TWO profiles (PlexA/PlexB), each its own HDHomeRun device + DVR in Plex. Plex merges every DVR
into a single guide, so the split is invisible in the UI.

THE SPEC (Pat): American sports and top soccer leagues prioritized; all major leagues and
conferences included; all NFL, all MLB; ALL 4K/UHD channels; prefer the 4K/higher-quality copy
of a channel over lower; cable fills whatever room remains; drop any channel that shows the same
programme for 24 hours straight (the FAST-loop channels).

Not included, called out honestly: NCAA basketball/baseball per-game slot groups (250/200/149
slots — they alone would need a third tuner; the marquee games air on the ESPN/SEC/ACC/BTN
linear networks which ARE here) and the F1 TV groups (~130 slots, not asked for). Add a third
tuner if these are wanted.
"""
import re
from datetime import timedelta

from django.utils import timezone

from apps.channels.models import Channel, ChannelGroup, ChannelProfile, ChannelProfileMembership
from apps.epg.models import ProgramData

BUDGET_PER_TUNER = 520
PROFILES = ("PlexA", "PlexB")

# ---- floor: everything here is included unconditionally (loopers excepted) ----
FLOOR_PREFIX = [
    # linear sports networks — where the leagues actually air
    "USA | Sports", "UK | Sky Sports", "UK | TNT Sports", "UK | Sports",
    "CA | Sports", "CA | Sportsnet",
    # every team feed: all NFL, all MLB, plus NBA/NHL equivalents
    "USA | NFL Teams", "USA | MLB Teams", "USA | NBA Teams", "USA | NHL Teams",
    # league game-slot groups: majors + conferences
    "USA | MLB ", "USA | NHL ", "USA | NBA ", "USA | NCAAF",
    "USA | SEC+", "USA | BIG10", "USA | MLS ",
    # top soccer
    "Live | English Premier League", "Live | La Liga", "Live | Ligue1",
    # ALL 4K/UHD
    "4K / UHD",
]
# cable fill, best first, into whatever room remains
CABLE_PREFIX = [
    "USA | Entertainment", "USA | News", "USA | Movies", "USA | Documentary",
    "UK | Entertainment", "UK | News", "UK | Movies", "UK | Documentary",
    "CA | Entertainment", "CA | Movies", "CA | Documentary",
]
VETO_GROUP = ["Backup", "ESPN+", "Pay-Per View", "NEXT PRO"]

NON_ENGLISH = re.compile(r"^(?!US|USA|UK|CA|EN)[A-Z]{2}\s*[:|]")
QUALITY = re.compile(r"\s*\b(UHD|4K|FHD|HD|SD|HEVC|H265|1080p?|720p?|"
                     r"\(5\.1 \+ Stereo\)|5\.1|Stereo|\(Events? Only\))\b\s*", re.I)
PREFIX = re.compile(r"^(US|USA|UK|CA|EN)\s*[:|]\s*", re.I)

# Pat: "if a 4k channel is available you need to keep that over SD" — highest quality wins.
def rank(name):
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


# ---- 24h-looper detection ----
now = timezone.now()
titles_by_epg = {}
for epg_id, title in (ProgramData.objects
                      .filter(start_time__lt=now + timedelta(hours=24), end_time__gt=now)
                      .values_list("epg_id", "title")):
    titles_by_epg.setdefault(epg_id, set()).add(title)


def is_looper(ch):
    if not ch.epg_data_id:
        return False              # game-slot feeds legitimately have no EPG; not loopers
    t = titles_by_epg.get(ch.epg_data_id)
    return t is not None and len(t) <= 1


selected = {}                     # dedupe key -> Channel
loopers = []

# floor: 4K group keeps every non-looper (no English filter, no cross-variant dedupe — Pat wants
# ALL of it); other floor groups are English-only with best-quality-variant dedupe.
for g in groups_for(FLOOR_PREFIX):
    fourk = g.name.startswith("4K")
    for c in g.channels.all():
        if not fourk and NON_ENGLISH.match(c.name):
            continue
        if is_looper(c):
            loopers.append(c.name)
            continue
        k = ("4k::" + c.name.lower()) if fourk else base_name(c.name)
        if k not in selected or rank(c.name) < rank(selected[k].name):
            selected[k] = c

floor_n = len(selected)
budget = BUDGET_PER_TUNER * len(PROFILES)
print("floor: %d channels (budget %d)" % (floor_n, budget))
assert floor_n <= budget, "floor exceeds two-tuner budget — needs a third tuner"

# cable fill
room = budget - floor_n
for prefix in CABLE_PREFIX:
    if room <= 0:
        break
    pool = []
    for c in Channel.objects.filter(channel_group__in=groups_for([prefix])):
        if NON_ENGLISH.match(c.name) or is_looper(c) or base_name(c.name) in selected:
            if is_looper(c):
                loopers.append(c.name)
            continue
        pool.append((rank(c.name), c.name, c))
    pool.sort(key=lambda t: (t[0], t[1]))
    for _, _, c in pool[:room]:
        selected[base_name(c.name)] = c
    room = budget - len(selected)
    print("  after %-22s -> %d selected (room %d)" % (prefix, len(selected), room))

print("TOTAL: %d | loopers dropped: %d" % (len(selected), len(loopers)))

# ---- split across the two profiles by stable channel number (guide merges them anyway) ----
chans = sorted(selected.values(), key=lambda c: (c.channel_number or 0, c.id))
halves = {PROFILES[0]: chans[:BUDGET_PER_TUNER], PROFILES[1]: chans[BUDGET_PER_TUNER:]}
for name, chs in halves.items():
    keep = {c.id for c in chs}
    prof, _ = ChannelProfile.objects.get_or_create(name=name)
    have = set(ChannelProfileMembership.objects
               .filter(channel_profile=prof).values_list("channel_id", flat=True))
    missing = [ChannelProfileMembership(channel_profile=prof, channel_id=cid,
                                        enabled=(cid in keep))
               for cid in Channel.objects.values_list("id", flat=True) if cid not in have]
    if missing:
        ChannelProfileMembership.objects.bulk_create(missing, batch_size=2000)
    on = ChannelProfileMembership.objects.filter(channel_profile=prof,
                                                 channel_id__in=keep).update(enabled=True)
    ChannelProfileMembership.objects.filter(channel_profile=prof)\
                                    .exclude(channel_id__in=keep).update(enabled=False)
    epg = Channel.objects.filter(id__in=keep, epg_data__isnull=False).count()
    print("%s: %d channels (%d with EPG)" % (name, on, epg))
