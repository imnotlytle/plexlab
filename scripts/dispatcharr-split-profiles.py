"""Split the curated 1,005-channel selection into two Dispatcharr profiles for Plex.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

WHY TWO PROFILES: Plex saves a tuner's channel map in a single request URI, and its server
rejects URIs over ~40 KB — about 500 channels' worth of mapping parameters. (The web wizard hits
the same wall around 455 channels; see PLAN.md.) The channelmap PUT REPLACES the whole map, so
chunking does not accumulate — one tuner simply cannot hold 1,005 channels. Two tuners, each with
its own DVR and profile-scoped guide, sail under the limit, and Plex merges both into one guide UI.

Channel NUMBERS are stable in Dispatcharr (assigned per Channel, not per profile), so mappings
survive profile membership changes.

Split rule: sports groups -> "PlexSports"; entertainment/news/movies/docs -> "PlexTV".
Both reuse the same curation (English-only, deduped, no event-slot groups) as the "Plex" profile,
which is left in place untouched.
"""
from apps.channels.models import Channel, ChannelProfile, ChannelProfileMembership

# The split is an internal tuner boundary only — Plex merges both DVRs into one guide, so which
# side a group lands on is invisible to the user. Documentary + UK News ride with sports purely
# to balance the two sides under the ~500-channel/one-PUT budget (405/600 rebalanced to 492/513).
SPORTS_GROUP_PREFIX = [
    "USA | Sports", "UK | Sky Sports", "UK | TNT Sports", "UK | Sports",
    "CA | Sports", "CA | Sportsnet",
    "USA | NFL Teams", "USA | MLB Teams", "USA | NBA Teams", "USA | NHL Teams",
    "USA | Documentary", "UK | Documentary", "CA | Documentary", "UK | News",
]

# start from the already-curated selection in the "Plex" profile
base_ids = list(ChannelProfileMembership.objects
                .filter(channel_profile__name="Plex", enabled=True)
                .values_list("channel_id", flat=True))
channels = Channel.objects.filter(id__in=base_ids).select_related("channel_group")

sports, tv = set(), set()
for c in channels:
    g = c.channel_group.name if c.channel_group else ""
    (sports if any(g.startswith(p) for p in SPORTS_GROUP_PREFIX) else tv).add(c.id)

print("base: %d -> sports %d | tv %d" % (len(base_ids), len(sports), len(tv)))
assert len(sports) <= 520 and len(tv) <= 520, "a side exceeds the one-PUT URI budget; rebalance"

for name, keep in (("PlexSports", sports), ("PlexTV", tv)):
    prof, _ = ChannelProfile.objects.get_or_create(name=name)
    have = set(ChannelProfileMembership.objects
               .filter(channel_profile=prof).values_list("channel_id", flat=True))
    missing = [ChannelProfileMembership(channel_profile=prof, channel_id=cid,
                                        enabled=(cid in keep))
               for cid in Channel.objects.values_list("id", flat=True) if cid not in have]
    if missing:
        ChannelProfileMembership.objects.bulk_create(missing, batch_size=2000)
    on = ChannelProfileMembership.objects.filter(channel_profile=prof, channel_id__in=keep)\
                                         .update(enabled=True)
    off = ChannelProfileMembership.objects.filter(channel_profile=prof)\
                                          .exclude(channel_id__in=keep).update(enabled=False)
    print("%s: enabled %d, disabled %d" % (name, on, off))
