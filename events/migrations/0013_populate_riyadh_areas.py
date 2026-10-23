from django.db import migrations
from django.utils import timezone
from django.utils.dateparse import parse_datetime


CENTER_LAT = 24.7136
CENTER_LON = 46.6753

CENTRAL_TERMS = [
    "masmak",
    "deera",
    "zal",
    "thumairi",
    "muaiq",
    "national museum",
    "historical center",
    "murabba",
    "malaz",
    "faisaliah",
    "king fahad national library",
]
NORTH_TERMS = [
    "riyadh park",
    "nakheel",
    "granada",
    "roshn",
    "riyadh front",
    "kafd",
    "u walk",
    "boulevard",
    "wonder garden",
    "winter wonderland",
    "king salman park",
    "kingdom centre",
    "olaya",
]
EAST_TERMS = [
    "rawdat khuraim",
    "king fahd stadium",
    "aviation museum",
    "al nahda",
]
SOUTH_TERMS = [
    "wadi namar",
    "red sand",
    "heet cave",
    "manakh",
]
WEST_TERMS = [
    "diriyah",
    "turaif",
    "bujairi",
    "salwa",
    "tuwaiq",
    "edge of the world",
    "qiddiya",
    "hidden valley",
]


def assign_area(event):
    text = f"{event.title or ''} {event.description or ''} {event.location or ''}".lower()

    for term in CENTRAL_TERMS:
        if term in text:
            return "Central Riyadh"
    for term in WEST_TERMS:
        if term in text:
            return "West Riyadh"
    for term in NORTH_TERMS:
        if term in text:
            return "North Riyadh"
    for term in EAST_TERMS:
        if term in text:
            return "East Riyadh"
    for term in SOUTH_TERMS:
        if term in text:
            return "South Riyadh"

    lat = event.latitude
    lon = event.longitude
    if lat is None or lon is None:
        return "Central Riyadh"

    lat = float(lat)
    lon = float(lon)
    if abs(lat - CENTER_LAT) < 0.035 and abs(lon - CENTER_LON) < 0.035:
        return "Central Riyadh"

    delta_lat = (lat - CENTER_LAT) * 111
    delta_lon = (lon - CENTER_LON) * 102
    if abs(delta_lat) >= abs(delta_lon):
        return "North Riyadh" if delta_lat > 0 else "South Riyadh"
    return "East Riyadh" if delta_lon > 0 else "West Riyadh"


def dt(value):
    parsed = parse_datetime(value)
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.utc)
    return parsed


def populate_areas(apps, schema_editor):
    Event = apps.get_model("events", "Event")

    updates = []
    for event in Event.objects.all():
        area = assign_area(event)
        if event.area != area:
            event.area = area
            updates.append(event)

    if updates:
        Event.objects.bulk_update(updates, ["area"])

    Event.objects.update_or_create(
        title="Al Muaiqiliyah Market",
        defaults={
            "category": "shopping",
            "area": "Central Riyadh",
            "description": (
                "A traditional market area in central Riyadh near historic souqs "
                "and heritage landmarks."
            ),
            "date": dt("2025-05-02T12:00:00Z"),
            "location": "Central Riyadh, Saudi Arabia",
            "start_date": None,
            "end_date": None,
            "start_time": None,
            "end_time": None,
            "price_range": "",
            "price": None,
            "rating": 4.6,
            "latitude": 24.6322,
            "longitude": 46.7142,
            "source": "curated",
            "source_url": "",
            "is_active": True,
            "tourism_relevance": 4,
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0012_event_area"),
    ]

    operations = [
        migrations.RunPython(populate_areas, noop_reverse),
    ]
