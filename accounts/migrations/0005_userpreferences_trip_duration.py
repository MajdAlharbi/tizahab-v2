from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_add_min_rating"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="trip_duration",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Number of trip days (1-30). Used by multi-day plan generation.",
            ),
        ),
    ]
