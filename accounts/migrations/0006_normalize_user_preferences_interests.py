from django.db import migrations


LEGACY_CATEGORY_ALIASES = {
    "restaurant": "food",
    "cafe": "food",
    "fast_food": "food",
    "dessert": "food",
    "bakery": "food",
    "juice": "food",
    "food_truck": "food",
    "outdoor": "nature",
    "other": "entertainment",
    "mall": "shopping",
    "museum": "heritage",
}


def normalize_interest(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"culture", "heritage", "entertainment", "food", "shopping", "nature", "family", "events"}:
        return normalized
    return LEGACY_CATEGORY_ALIASES.get(normalized, normalized or "events")


def normalize_interests(apps, schema_editor):
    UserPreferences = apps.get_model("accounts", "UserPreferences")

    for preference in UserPreferences.objects.all().iterator():
        interests = preference.interests or []
        normalized = []
        for value in interests:
            mapped = normalize_interest(value)
            if mapped and mapped not in normalized:
                normalized.append(mapped)
        preference.interests = normalized
        preference.save(update_fields=["interests"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userpreferences_trip_duration"),
    ]

    operations = [
        migrations.RunPython(normalize_interests, migrations.RunPython.noop),
    ]
