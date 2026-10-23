import json
from pathlib import Path

from django.db import migrations
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_time


SYNC_FIELDS = [
    "category",
    "description",
    "date",
    "start_date",
    "end_date",
    "start_time",
    "end_time",
    "location",
    "area",
    "price_range",
    "price",
    "latitude",
    "longitude",
    "rating",
    "image_url",
    "source",
    "source_url",
    "is_active",
    "tourism_relevance",
]


def parse_dt(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.utc)
    return parsed


def fixture_records():
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "riyadh_places.json"
    with fixture_path.open(encoding="utf-8-sig") as fixture_file:
        return json.load(fixture_file)


def clean_and_sync_places(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    records = fixture_records()
    verified_titles = {record["fields"]["title"] for record in records}

    # Remove broad placeholder entries that were not confirmed as specific Riyadh places.
    Event.objects.exclude(title__in=verified_titles).delete()

    for record in records:
        fields = record["fields"]
        defaults = {field: fields.get(field) for field in SYNC_FIELDS}
        defaults["date"] = parse_dt(defaults["date"])
        defaults["start_date"] = parse_dt(defaults["start_date"])
        defaults["end_date"] = parse_dt(defaults["end_date"])
        defaults["start_time"] = parse_time(defaults["start_time"]) if defaults["start_time"] else None
        defaults["end_time"] = parse_time(defaults["end_time"]) if defaults["end_time"] else None

        matches = Event.objects.filter(title=fields["title"]).order_by("id")
        event = matches.first()
        if event:
            matches.exclude(id=event.id).delete()
            for field, value in defaults.items():
                setattr(event, field, value)
            event.save(update_fields=SYNC_FIELDS)
        else:
            Event.objects.create(title=fields["title"], **defaults)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0015_populate_event_image_urls"),
    ]

    operations = [
        migrations.RunPython(clean_and_sync_places, noop_reverse),
    ]
