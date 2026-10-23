from django.db import migrations


def _slot_type_for_index(index, total):
    if total <= 0:
        return "activity"
    if total == 1:
        return "breakfast"
    if total == 2:
        return "breakfast" if index == 0 else "evening"
    if total == 3:
        if index == 0:
            return "breakfast"
        if index == 1:
            return "activity"
        return "evening"

    last_index = total - 1
    lunch_index = min(3, last_index - 1)
    if index == 0:
        return "breakfast"
    if index == lunch_index:
        return "lunch"
    if index == last_index:
        return "evening"
    return "activity"


def backfill_daily_plan_items(apps, schema_editor):
    DailyPlan = apps.get_model("daily_plan", "DailyPlan")
    DailyPlanItem = apps.get_model("daily_plan", "DailyPlanItem")
    through_model = DailyPlan.events.through

    for plan in DailyPlan.objects.all():
        ordered_event_ids = list(
            through_model.objects
            .filter(dailyplan_id=plan.id)
            .order_by("id")
            .values_list("event_id", flat=True)
        )
        total = len(ordered_event_ids)
        if not total:
            continue

        existing_event_ids = set(
            DailyPlanItem.objects.filter(plan_id=plan.id).values_list("event_id", flat=True)
        )
        for index, event_id in enumerate(ordered_event_ids):
            if event_id in existing_event_ids:
                continue
            DailyPlanItem.objects.create(
                plan_id=plan.id,
                event_id=event_id,
                slot_type=_slot_type_for_index(index, total),
                order=index,
                source="generated",
                locked=False,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("daily_plan", "0003_dailyplanitem"),
    ]

    operations = [
        migrations.RunPython(backfill_daily_plan_items, migrations.RunPython.noop),
    ]
