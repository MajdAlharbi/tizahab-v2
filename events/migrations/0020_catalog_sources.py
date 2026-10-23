from django.db import migrations


def create_sources(apps, schema_editor):
    Source = apps.get_model("events", "CatalogSource")
    for provider in ("osm", "ticketmaster"):
        Source.objects.using(schema_editor.connection.alias).get_or_create(
            provider=provider, defaults={"enabled": False}
        )


class Migration(migrations.Migration):
    dependencies = [("events", "0019_catalogsource_event_last_verified_at_and_more")]
    operations = [migrations.RunPython(create_sources, migrations.RunPython.noop)]
