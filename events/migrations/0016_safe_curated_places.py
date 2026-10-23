"""Replace the pending destructive data operation without replaying applied work."""

import json
from pathlib import Path

from django.db import migrations


def add_missing_places(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    events = Event.objects.using(schema_editor.connection.alias)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "riyadh_places.json"
    with fixture.open(encoding="utf-8-sig") as source:
        records = json.load(source)
    allowed = {field.name for field in Event._meta.concrete_fields} - {"id"}
    existing_titles = set(events.values_list("title", flat=True))
    for record in records:
        fields = record["fields"]
        if fields["title"] in existing_titles:
            continue
        events.create(**{key: value for key, value in fields.items() if key in allowed})
        existing_titles.add(fields["title"])


class Migration(migrations.Migration):
    # One replacement per historical migration also protects partially upgraded DBs.
    replaces = [("events", "0016_curate_verified_places")]
    dependencies = [("events", "0015_populate_event_image_urls")]
    operations = [migrations.RunPython(add_missing_places, migrations.RunPython.noop)]
