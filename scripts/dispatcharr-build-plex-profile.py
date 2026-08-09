"""Build the 'Plex' channel profile in Dispatcharr: sports + English linear TV.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

WHY THIS EXISTS: the provider ships ~14,700 channels. Handing all of that to Plex makes the guide
unusable - Plex is built around a few hundred linear channels, not fifteen thousand. Worse, most of
the volume is per-event placeholder slots ("NCAAF 02 :", "ESPN+ 07: Sparta vs Feyenoord @ 6:10AM")
which are empty most of the time and would fill the guide with dead rows.

So the profile keeps two things:
  1. Real 24/7 linear channels - ESPN, ACC Network, Sky Sports, AMC, news, 4K.
  2. The numbered game-feed groups for the big leagues, which DO carry live games (MLB/NHL/NBA/
     NCAAF). These look ugly in a guide but they are how you actually watch a game on IPTV.

Everything else - the ESPN+/Disney+/Prime/Pluto/PlexTV VOD dumps, the "Backup" duplicates, the
NCAA basketball/baseball hundreds - is left out. It stays in Dispatcharr, just not exposed to Plex,
so widening the selection later is a one-line change here.
"""
from apps.channels.models import Channel, ChannelGroup, ChannelProfile, ChannelProfileMembership

PROFILE = "Plex"

# Real linear channels. Prefix match - the group names carry trailing emoji.
KEEP_PREFIX = [
    "USA | Sports",          # ESPN, ACC Network, regional sports networks
    "USA | Entertainment",
    "USA | News",
    "USA | Movies",
    "USA | Documentary",
    "USA | NFL Teams",       # per-team CBS/FOX affiliate feeds - real broadcast, not placeholder
    "4K / UHD",
    "UK | Sky Sports",       # also catches "UK | Sky Sports+"
    "UK | TNT Sports",
    "UK | Sports",
    "CA | Sports",
    "CA | Sportsnet",
]

# Numbered per-game feeds worth carrying for the leagues Pat actually watches.
KEEP_GAME_FEEDS = [
    "USA | MLB ",
    "USA | NHL ",
    "USA | NBA ",
    "USA | NCAAF",
]

# Vetoes, applied after the keeps. "Backup" groups are duplicate feeds of the same games and would
# double every entry; the rest are VOD/event dumps that are mostly empty.
VETO_SUBSTR = [
    "Backup", "Event", "ESPN+", "Prime", "PlexTV", "Pluto", "Disney+",
    "MILB", "SEC+", "BIG10", "Peacock", "Dazn", "Paramount+", "NCAA MEN",
    "NCAA WOMEN", "NCAA BASEBALL", "Pay-Per View", "Telemundo",
]


def wanted(name):
    if any(v.lower() in name.lower() for v in VETO_SUBSTR):
        return False
    return any(name.startswith(p) for p in KEEP_PREFIX + KEEP_GAME_FEEDS)


profile, created = ChannelProfile.objects.get_or_create(name=PROFILE)
print("profile %r %s (id %s)" % (PROFILE, "created" if created else "reused", profile.id))

groups = [g for g in ChannelGroup.objects.all() if wanted(g.name)]
keep_ids = set(
    Channel.objects.filter(channel_group__in=groups).values_list("id", flat=True)
)
print("matched %d groups -> %d channels (of %d total)"
      % (len(groups), len(keep_ids), Channel.objects.count()))

# Memberships may be auto-created for every channel; make sure one exists for each, then flip
# `enabled` so only the selection is exposed through this profile's HDHomeRun lineup.
existing = dict(
    ChannelProfileMembership.objects
    .filter(channel_profile=profile)
    .values_list("channel_id", "id")
)
missing = [
    ChannelProfileMembership(channel_profile=profile, channel_id=cid, enabled=(cid in keep_ids))
    for cid in Channel.objects.values_list("id", flat=True) if cid not in existing
]
if missing:
    ChannelProfileMembership.objects.bulk_create(missing, batch_size=2000)
    print("created %d memberships" % len(missing))

on = ChannelProfileMembership.objects.filter(channel_profile=profile, channel_id__in=keep_ids)
off = ChannelProfileMembership.objects.filter(channel_profile=profile).exclude(channel_id__in=keep_ids)
print("enabled ->", on.update(enabled=True), "| disabled ->", off.update(enabled=False))

print("\ngroups included:")
for g in sorted(groups, key=lambda x: x.name):
    print("   %5d  %s" % (g.channels.count(), g.name))
