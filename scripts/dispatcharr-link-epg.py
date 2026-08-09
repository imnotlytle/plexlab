"""Link Dispatcharr channels to their EPG entries by tvg_id, then pull the programme data.

Run inside the container:
    docker exec -i dispatcharr python3 /app/manage.py shell < this-file

WHY THIS EXISTS: Dispatcharr's built-in `match_epg_channels` task does fuzzy name matching for
channels that have no tvg_id. It does NOT link channels whose tvg_id already matches an EPG entry
exactly - which is the case for ~856 of the 860 tagged channels from this provider. Left alone,
the EPG source reports "No channels mapped" forever and Plex shows an empty guide.

Matching is exact-first, then case-insensitive, because the provider's playlist and its own XMLTV
disagree on capitalisation ('SkySportsF1UHD.uk' vs 'skysportsf1.uk').
"""
from apps.channels.models import Channel
from apps.epg.models import EPGData, EPGSource, ProgramData
from apps.epg.tasks import refresh_epg_data

epg_by_id = {}
epg_by_lower = {}
for e in EPGData.objects.all().only("id", "tvg_id"):
    if not e.tvg_id:
        continue
    epg_by_id.setdefault(e.tvg_id, e.id)
    epg_by_lower.setdefault(e.tvg_id.lower(), e.id)

todo = (Channel.objects
        .exclude(tvg_id__isnull=True).exclude(tvg_id="")
        .filter(epg_data__isnull=True)
        .only("id", "tvg_id"))

exact = ci = 0
updates = []
for c in todo:
    eid = epg_by_id.get(c.tvg_id)
    if eid:
        exact += 1
    else:
        eid = epg_by_lower.get(c.tvg_id.lower())
        if eid:
            ci += 1
    if eid:
        c.epg_data_id = eid
        updates.append(c)

Channel.objects.bulk_update(updates, ["epg_data"], batch_size=1000)
print("linked %d channels  (exact %d, case-insensitive %d)" % (len(updates), exact, ci))
print("channels now linked to EPG:", Channel.objects.filter(epg_data__isnull=False).count())

# Programme data is only fetched for EPG entries that something is actually mapped to, so this
# has to run AFTER the links exist.
for src in EPGSource.objects.filter(is_active=True):
    refresh_epg_data.delay(src.id)
    print("queued programme fetch for EPG source", src.id, src.name)
print("programmes before fetch:", ProgramData.objects.count())
