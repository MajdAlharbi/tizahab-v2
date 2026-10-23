from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_normalize_user_preferences_interests"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userpreferences",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
