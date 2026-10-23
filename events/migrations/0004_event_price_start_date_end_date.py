import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_event_latitude_event_longitude_alter_event_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="start_date",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="end_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(
                fields=["category", "date"], name="events_even_categor_idx"
            ),
        ),
    ]
