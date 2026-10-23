from importlib import import_module

from django.db import migrations


sync_migration = import_module("events.migrations.0016_curate_verified_places")
clean_and_sync_places = sync_migration.clean_and_sync_places
noop_reverse = sync_migration.noop_reverse


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0016_curate_verified_places"),
    ]

    operations = [
        migrations.RunPython(clean_and_sync_places, noop_reverse),
    ]
