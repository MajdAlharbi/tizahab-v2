from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0013_populate_riyadh_areas"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="image_url",
            field=models.URLField(blank=True, default="", max_length=500),
        ),
    ]
