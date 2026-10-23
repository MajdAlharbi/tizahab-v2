"""Copy legacy plans; never rewrite or remove the original plan/item records."""

from django.db import migrations


def preserve_legacy_trips(apps, schema_editor):
    alias = schema_editor.connection.alias
    Plan = apps.get_model("daily_plan", "DailyPlan")
    Item = apps.get_model("daily_plan", "DailyPlanItem")
    Trip = apps.get_model("daily_plan", "Trip")
    Day = apps.get_model("daily_plan", "TripDay")
    Activity = apps.get_model("daily_plan", "TripActivity")
    Prefs = apps.get_model("accounts", "UserPreferences")
    for plan in Plan.objects.using(alias).all().iterator():
        preferences = Prefs.objects.using(alias).filter(user_id=plan.user_id).first()
        snapshot = {
            "interests": preferences.interests if preferences else [],
            "budget_min": preferences.budget_min if preferences else None,
            "budget_max": preferences.budget_max if preferences else None,
            "min_rating": (
                float(preferences.min_rating)
                if preferences and preferences.min_rating is not None
                else None
            ),
            "preferred_language": (
                preferences.preferred_language if preferences else "en"
            ),
        }
        trip, created = Trip.objects.using(alias).get_or_create(
            legacy_plan_id=plan.pk,
            defaults={
                "user_id": plan.user_id,
                "name": f"Riyadh · {plan.date}",
                "start_date": plan.date,
                "duration": 1,
                "preferences": snapshot,
            },
        )
        if not created:
            continue
        day = Day.objects.using(alias).create(
            trip_id=trip.pk, position=0, date=plan.date
        )
        seen = set()
        for item in (
            Item.objects.using(alias).filter(plan_id=plan.pk).order_by("order", "pk")
        ):
            Activity.objects.using(alias).create(
                trip_id=trip.pk,
                day_id=day.pk,
                key=f"legacy-item-{item.pk}",
                event_id=item.event_id,
                slot_type=item.slot_type,
                position=item.order,
                source=item.source,
                locked=item.locked,
                override_preferences=True,
            )
            seen.add(item.event_id)
        through = Plan.events.through
        for row in (
            through.objects.using(alias).filter(dailyplan_id=plan.pk).order_by("pk")
        ):
            if row.event_id not in seen:
                Activity.objects.using(alias).create(
                    trip_id=trip.pk,
                    day_id=day.pk,
                    key=f"legacy-link-{row.pk}",
                    event_id=row.event_id,
                    slot_type="activity",
                    position=len(seen),
                    source="manual",
                    override_preferences=True,
                )
                seen.add(row.event_id)


class Migration(migrations.Migration):
    dependencies = [
        (
            "daily_plan",
            "0005_trip_tripday_tripactivity_trip_trip_duration_1_30_and_more",
        ),
        ("accounts", "0007_userpreferences_start_date_userpreferences_end_date"),
    ]
    operations = [
        migrations.RunPython(preserve_legacy_trips, migrations.RunPython.noop)
    ]
