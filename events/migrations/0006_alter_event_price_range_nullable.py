from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Make price_range nullable to match the model definition.
    Migration 0002 added it as NOT NULL with default=''; the model has null=True, blank=True.
    """

    dependencies = [
        ("events", "0005_event_created_at_updated_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="price_range",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
