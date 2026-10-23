from importlib import import_module

from django.db import migrations


add_missing_places = import_module(
    "events.migrations.0016_safe_curated_places"
).add_missing_places


class Migration(migrations.Migration):
    replaces = [("events", "0017_expand_verified_riyadh_places")]
    dependencies = [("events", "0016_curate_verified_places")]
    operations = [migrations.RunPython(add_missing_places, migrations.RunPython.noop)]
