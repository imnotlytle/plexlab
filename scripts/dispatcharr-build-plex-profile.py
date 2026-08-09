"""Build the 'Plex' channel profile in Dispatcharr: English-language sports, deduplicated.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

WHY IT IS THIS SMALL: the provider ships ~14,700 channels. A first attempt exposed 1,180 of them
and Plex's tuner wizard failed with "There was a problem saving channel mappings" - Plex's Live TV
is built for a few hundred linear channels, not thousands. So this starts at the minimum that is
actually useful (sports Pat asked for), proves the pipeline end to end, and can be widened after.

Three filters do the work:
  1. GROUPS      - sports groups only, and only real linear channels. The numbered per-event slots
                   ("NCAAF 02 :", "ESPN+ 07: Sparta vs Feyenoord @ 6:10AM") are excluded: they are
                   empty most of the time, carry no EPG, and would bury the guide in dead rows.
  2. ENGLISH     - the 4K group in particular is full of DE:/FR:/IL:/BG: channels. Keep US/UK/CA.
  3. DEDUPE      - the provider carries the same channel several times at different qualities
                   ("Sky Sports Main Event" appears 4x as UHD/FHD/HD/plain). Keep ONE, preferring
                   FHD then HD. 4K is deliberately deprioritised: this NAS is an N100 and live 4K
                   transcoding would flatten it.

To widen later, add group prefixes to KEEP_PREFIX and re-run - it is idempotent.
"""
import re

from apps.channels.models import Channel, ChannelGroup, ChannelProfile, ChannelProfileMembership

PROFILE = "Plex"

KEEP_PREFIX = [
    # sports
    "USA | Sports",        # ESPN, ACC Network, regional sports networks
    "UK | Sky Sports",     # also matches "UK | Sky Sports+"
    "UK | TNT Sports",
    "UK | Sports",
    "CA | Sports",
    "CA | Sportsnet",
    "USA | NFL Teams",     # per-team CBS/FOX affiliate feeds - real broadcast, not placeholders
    "USA | MLB Teams",
    "USA | NBA Teams",
    "USA | NHL Teams",
    # general English TV
    "USA | Entertainment",
    "USA | News",
    "USA | Movies",
    "USA | Documentary",
    "UK | Entertainment",
    "UK | Documentary",
    "UK | Movies",
    "UK | News",
    "CA | Entertainment",
    "CA | Documentary",
    "CA | Movies",
]
# "4K / UHD" is deliberately NOT here: only ~a third of it is sports (the rest is Stingray/
# Travel XP/BRTV 8K), it is where non-English channels leak in, and live 4K transcoding would
# flatten an N100. Add it back only if 4K sports feeds are specifically wanted.
#
# The numbered per-event groups (ESPN+, NCAAF, MLB/NHL/NBA game slots, *Events, *Backup) stay out:
# they are empty placeholders most of the time and carry no EPG, so they add guide clutter rather
# than watchable channels. The *Teams* groups above ARE included - those are real affiliate feeds.

VETO_GROUP = ["Backup", "Event", "ESPN+", "Pay-Per View"]

# Channel-name prefixes we accept. Anything with a non-English country prefix is dropped.
ENGLISH_PREFIX = re.compile(r"^(US|USA|UK|CA)\s*[:|]", re.I)
NON_ENGLISH_PREFIX = re.compile(r"^[A-Z]{2}\s*[:|]")

QUALITY = re.compile(
    r"\s*\b(UHD|4K|FHD|HD|SD|HEVC|H265|1080p?|720p?|"
    r"\(5\.1 \+ Stereo\)|5\.1|Stereo|\(Events? Only\))\b\s*", re.I)
PREFIX = re.compile(r"^(US|USA|UK|CA|EN)\s*[:|]\s*", re.I)


def english(name):
    if ENGLISH_PREFIX.match(name):
        return True
    return not NON_ENGLISH_PREFIX.match(name)      # unprefixed names are assumed English


def base_name(name):
    n = QUALITY.sub(" ", PREFIX.sub("", name))
    return re.sub(r"\s+", " ", n).strip(" -|:").lower()


def rank(name):
    """Lower is better. Prefer FHD, then HD, then plain; push 4K/UHD last (N100 can't transcode it)."""
    low = name.lower()
    if "fhd" in low:
        return 0
    if re.search(r"\bhd\b", low) and "uhd" not in low:
        return 1
    if "4k" in low or "uhd" in low:
        return 3
    return 2


groups = [g for g in ChannelGroup.objects.all()
          if any(g.name.startswith(p) for p in KEEP_PREFIX)
          and not any(v.lower() in g.name.lower() for v in VETO_GROUP)]

candidates = [c for c in Channel.objects.filter(channel_group__in=groups) if english(c.name)]

best = {}
for c in candidates:
    key = base_name(c.name)
    if key not in best or rank(c.name) < rank(best[key].name):
        best[key] = c
keep_ids = {c.id for c in best.values()}

profile, created = ChannelProfile.objects.get_or_create(name=PROFILE)
print("profile %r %s" % (PROFILE, "created" if created else "reused"))
print("groups: %d | english candidates: %d | after dedupe: %d  (library total %d)"
      % (len(groups), len(candidates), len(keep_ids), Channel.objects.count()))

existing = set(ChannelProfileMembership.objects
               .filter(channel_profile=profile).values_list("channel_id", flat=True))
missing = [ChannelProfileMembership(channel_profile=profile, channel_id=cid,
                                    enabled=(cid in keep_ids))
           for cid in Channel.objects.values_list("id", flat=True) if cid not in existing]
if missing:
    ChannelProfileMembership.objects.bulk_create(missing, batch_size=2000)

on = ChannelProfileMembership.objects.filter(channel_profile=profile, channel_id__in=keep_ids)
off = ChannelProfileMembership.objects.filter(channel_profile=profile).exclude(channel_id__in=keep_ids)
print("enabled ->", on.update(enabled=True), "| disabled ->", off.update(enabled=False))

with_epg = Channel.objects.filter(id__in=keep_ids, epg_data__isnull=False).count()
print("of those, linked to EPG:", with_epg)
print("\nsample:")
for c in sorted(best.values(), key=lambda x: x.name)[:15]:
    print("   ", c.name[:60])
