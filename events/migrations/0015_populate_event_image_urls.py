import json
from pathlib import Path
from urllib.parse import quote

from django.db import migrations


CATEGORY_TAGS = {
    "culture": "museum",
    "heritage": "heritage",
    "nature": "park",
    "food": "restaurant",
    "shopping": "mall",
    "events": "festival",
    "entertainment": "entertainment",
    "family": "park",
    "other": "riyadh",
}


def fallback_image(pk, category):
    tag = CATEGORY_TAGS.get(str(category or "").lower(), "riyadh")
    return f"https://loremflickr.com/1200/800/riyadh,{quote(tag)}?lock={pk}"


def load_fixture_images():
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "riyadh_places.json"
    if not fixture_path.exists():
        return {}

    with fixture_path.open(encoding="utf-8-sig") as fixture_file:
        records = json.load(fixture_file)

    images = {}
    for record in records:
        fields = record.get("fields", {})
        title = fields.get("title")
        image_url = fields.get("image_url")
        if title and image_url:
            images[title] = image_url
    return images


def populate_images(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    fixture_images = load_fixture_images()

    updates = []
    for event in Event.objects.all():
        image_url = fixture_images.get(event.title) or fallback_image(event.pk, event.category)
        if event.image_url != image_url:
            event.image_url = image_url
            updates.append(event)

    if updates:
        Event.objects.bulk_update(updates, ["image_url"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0014_event_image_url"),
    ]

    operations = [
        migrations.RunPython(populate_images, noop_reverse),
    ]
