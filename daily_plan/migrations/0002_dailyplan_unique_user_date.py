from django.conf import settings
from django.db import migrations


def deduplicate_daily_plans(apps, schema_editor):
    """
    Keep only the most recent DailyPlan for each (user, date) pair.
    Transfers events from duplicates to the surviving plan before deletion.
    """
    DailyPlan = apps.get_model("daily_plan", "DailyPlan")
    seen = {}
    for plan in DailyPlan.objects.order_by("user_id", "date", "-created_at"):
        key = (plan.user_id, plan.date)
        if key not in seen:
            seen[key] = plan
        else:
            # Merge events from the duplicate into the surviving plan
            surviving = seen[key]
            surviving.events.add(*plan.events.all())
            plan.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("daily_plan", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(deduplicate_daily_plans, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name="dailyplan",
            unique_together={("user", "date")},
        ),
    ]
