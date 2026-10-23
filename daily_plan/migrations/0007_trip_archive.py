from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("daily_plan", "0006_preserve_legacy_trips")]
    operations = [
        migrations.AddField(
            model_name="trip",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
