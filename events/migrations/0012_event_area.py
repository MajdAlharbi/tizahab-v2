from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0011_event_end_time_event_is_active_event_source_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="area",
            field=models.CharField(
                choices=[
                    ("Central Riyadh", "Central Riyadh"),
                    ("North Riyadh", "North Riyadh"),
                    ("East Riyadh", "East Riyadh"),
                    ("South Riyadh", "South Riyadh"),
                    ("West Riyadh", "West Riyadh"),
                ],
                db_index=True,
                default="Central Riyadh",
                max_length=50,
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["area", "category"], name="events_even_area_16e361_idx"),
        ),
    ]
