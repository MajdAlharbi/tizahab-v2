"""Validated trip documents shared by guest previews and private saved trips."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import UserPreferencesSerializer
from events.models import Event
from events.serializers import EventSerializer
from .serializers import EventIDField
from .services import generate_recommendations, build_plan_items_from_ordered_events


class TripInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, default="My Riyadh trip")
    start_date = serializers.DateField()
    duration = serializers.IntegerField(min_value=1, max_value=30)
    preferences = serializers.JSONField(default=dict)
    days = serializers.ListField(
        child=serializers.DictField(), max_length=30, default=list
    )
    unscheduled = serializers.ListField(
        child=serializers.DictField(), max_length=300, default=list
    )

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Preferences must be an object.")
        allowed = {
            k: v
            for k, v in value.items()
            if k
            in (
                "interests",
                "budget_min",
                "budget_max",
                "min_rating",
                "preferred_language",
            )
        }
        validator = UserPreferencesSerializer(data=allowed)
        validator.is_valid(raise_exception=True)
        result = {
            "interests": [],
            "budget_min": None,
            "budget_max": None,
            "min_rating": None,
            "preferred_language": "en",
            **validator.validated_data,
        }
        if result["min_rating"] is not None:
            result["min_rating"] = float(result["min_rating"])
        return result


def preference_warnings(event, preferences):
    warnings = []
    if preferences.get("interests") and event.category not in preferences["interests"]:
        warnings.append("Outside selected interests")
    if event.price is not None:
        if (
            preferences.get("budget_min") is not None
            and event.price < preferences["budget_min"]
        ):
            warnings.append("Below your price range")
        if (
            preferences.get("budget_max") is not None
            and event.price > preferences["budget_max"]
        ):
            warnings.append("Above your price range")
    if preferences.get("min_rating") is not None and (
        event.rating is None or event.rating < Decimal(str(preferences["min_rating"]))
    ):
        warnings.append("Below your minimum rating or rating unknown")
    return warnings


def validate_document(raw, *, allow_historical=False, check_availability=True):
    validator = TripInputSerializer(data=raw)
    validator.is_valid(raise_exception=True)
    data = validator.validated_data
    start = data["start_date"]
    if not allow_historical and start < timezone.localdate():
        raise serializers.ValidationError(
            {"start_date": "Choose today or a future date."}
        )
    data["start_date"] = start.isoformat()
    supplied = data["days"]
    if supplied and len(supplied) != data["duration"]:
        raise serializers.ValidationError(
            {"days": "Days must match the trip duration."}
        )
    data["days"] = supplied or [{"items": []} for _ in range(data["duration"])]
    seen_keys = set()
    for index, day in enumerate(data["days"]):
        day["date"] = (start + timedelta(days=index)).isoformat()
    containers = [
        (d, timezone.datetime.fromisoformat(d["date"]).date()) for d in data["days"]
    ]
    containers.append(({"items": data["unscheduled"]}, None))
    total = 0
    for container, assigned_date in containers:
        items = container.get("items", [])
        if not isinstance(items, list) or len(items) > (50 if assigned_date else 300):
            raise serializers.ValidationError(
                {"items": "A day supports up to 50 activities."}
            )
        day_events = set()
        clean = []
        for item in items:
            if not isinstance(item, dict):
                raise serializers.ValidationError({"items": "Invalid activity."})
            event_id = EventIDField().run_validation(item.get("event_id"))
            event = Event.objects.filter(pk=event_id).first()
            if event is None:
                raise serializers.ValidationError(
                    {"event_id": "This place no longer exists."}
                )
            if (
                check_availability
                and assigned_date
                and not event.is_available_on(assigned_date)
            ):
                raise serializers.ValidationError(
                    {
                        "availability": f"{event.title} is unavailable on {assigned_date}. Move it to Unscheduled Places."
                    }
                )
            if event_id in day_events:
                raise serializers.ValidationError(
                    {"event_id": "A place cannot appear twice on the same day."}
                )
            day_events.add(event_id)
            key = str(item.get("key") or uuid4())
            if len(key) > 64 or key in seen_keys:
                raise serializers.ValidationError(
                    {"key": "Activity keys must be unique and at most 64 characters."}
                )
            seen_keys.add(key)
            slot = serializers.ChoiceField(
                choices=["breakfast", "activity", "lunch", "evening"]
            ).run_validation(item.get("slot_type", "activity"))
            locked = serializers.BooleanField().run_validation(
                item.get("locked", False)
            )
            override = serializers.BooleanField().run_validation(
                item.get("override_preferences", False)
            )
            warnings = preference_warnings(event, data["preferences"])
            if item.get("source") == "manual" and warnings and not override:
                raise serializers.ValidationError(
                    {"preference_warning": warnings, "event_id": event_id}
                )
            clean.append(
                {
                    "key": key,
                    "event_id": event_id,
                    "event": EventSerializer(event).data,
                    "slot_type": slot,
                    "locked": locked,
                    "source": (
                        "manual" if item.get("source") == "manual" else "generated"
                    ),
                    "override_preferences": override,
                    "warnings": warnings,
                }
            )
            total += 1
        container["items"] = clean
        if assigned_date is None:
            data["unscheduled"] = clean
    if total > 500:
        raise serializers.ValidationError(
            {"items": "A trip supports up to 500 activities."}
        )
    return data


def _keys(document):
    return {item["key"] for day in document["days"] for item in day["items"]} | {
        item["key"] for item in document["unscheduled"]
    }


def preview_dates(raw, start_date, duration, confirmed=False):
    document = validate_document(raw, allow_historical=True, check_availability=False)
    date_validator = serializers.DateField()
    new_start = date_validator.run_validation(start_date)
    new_duration = serializers.IntegerField(min_value=1, max_value=30).run_validation(
        duration
    )
    if new_start < timezone.localdate():
        raise serializers.ValidationError(
            {"start_date": "Choose today or a future date."}
        )
    conflicts = []
    days = []
    moved = []
    for index, old_day in enumerate(document["days"]):
        new_date = new_start + timedelta(days=index)
        kept = []
        for item in old_day["items"]:
            event = Event.objects.get(pk=item["event_id"])
            if index >= new_duration or not event.is_available_on(new_date):
                conflicts.append(
                    {
                        "key": item["key"],
                        "title": event.title,
                        "locked": item["locked"],
                        "reason": (
                            "Removed day"
                            if index >= new_duration
                            else "Unavailable on new date"
                        ),
                    }
                )
                moved.append(item)
            else:
                kept.append(item)
        if index < new_duration:
            days.append({"items": kept})
    days.extend({"items": []} for _ in range(new_duration - len(days)))
    if conflicts and not confirmed:
        return {"requires_confirmation": True, "conflicts": conflicts}
    document.update(
        start_date=new_start.isoformat(),
        duration=new_duration,
        days=days,
        unscheduled=document["unscheduled"] + moved,
    )
    return {"trip": validate_document(document), "conflicts": conflicts}


def generate_document(raw, *, day_index=None, confirmed=False, user=None):
    document = validate_document(raw)
    if not document["preferences"]["interests"]:
        raise serializers.ValidationError(
            {"interests": "Choose at least one interest."}
        )
    indexes = (
        list(range(document["duration"]))
        if day_index is None
        else [
            serializers.IntegerField(
                min_value=0, max_value=document["duration"] - 1
            ).run_validation(day_index)
        ]
    )
    unlocked = [
        i
        for index in indexes
        for i in document["days"][index]["items"]
        if not i["locked"]
    ]
    if unlocked and not confirmed:
        return {
            "requires_confirmation": True,
            "conflicts": [
                {"title": i["event"]["title"], "reason": "Regenerate unlocked activity"}
                for i in unlocked
            ],
        }
    # Reserve all other days, locked activities, and unscheduled selections before
    # selecting any new place. The caller's date range never broadens availability.
    preferences = SimpleNamespace(**document["preferences"])
    preserved_days = []
    for index in indexes:
        day = document["days"][index]
        locked = [i for i in day["items"] if i["locked"]]
        reserved = {
            i["event_id"]
            for other_index, d in enumerate(document["days"])
            for i in d["items"]
            if other_index != index or i["locked"]
        }
        reserved.update(i["event_id"] for i in document["unscheduled"])
        from .services import _normalized_title

        reserved_titles = {
            _normalized_title(title)
            for title in Event.objects.filter(pk__in=reserved).values_list(
                "title", flat=True
            )
        }
        reserved.update(
            pk
            for pk, title in Event.objects.values_list("pk", "title")
            if _normalized_title(title) in reserved_titles
        )
        events = generate_recommendations(
            user,
            date_str=day["date"],
            seed=str(uuid4()),
            exclude_ids=reserved,
            preferences_override=preferences,
        )
        # This product does not silently widen explicit interests for support slots.
        events = [
            e for e in events if not preference_warnings(e, document["preferences"])
        ]
        specs = build_plan_items_from_ordered_events(events)
        capacity = max(5, len(day["items"])) - len(locked)
        new = [
            {
                "key": str(uuid4()),
                "event_id": spec["event"].id,
                "locked": False,
                "slot_type": spec["slot_type"],
                "source": "generated",
            }
            for spec in specs[: max(0, capacity)]
        ]
        if not new:
            # No result is not permission to erase the user's previous selections.
            preserved_days.append(index)
            reserved.update(i["event_id"] for i in day["items"])
            continue
        # Keep locks in the user's sequence: prepending all locks can put an
        # afternoon visit before breakfast after regeneration.
        replacements = iter(new)
        rebuilt = []
        for original in day["items"]:
            if original["locked"]:
                rebuilt.append(original)
            else:
                replacement = next(replacements, None)
                if replacement is not None:
                    rebuilt.append(replacement)
        rebuilt.extend(replacements)
        day["items"] = rebuilt
        reserved.update(i["event_id"] for i in day["items"])
    return {"trip": validate_document(document), "preserved_days": preserved_days}


def trip_document(trip):
    days = [
        {"date": day.date.isoformat(), "items": []}
        for day in trip.days.order_by("position")
    ]
    unscheduled = []
    for item in trip.activities.select_related("event", "day").order_by(
        "position", "pk"
    ):
        payload = {
            "key": item.key,
            "event_id": item.event_id,
            "event": EventSerializer(item.event).data,
            "slot_type": item.slot_type,
            "locked": item.locked,
            "source": item.source,
            "override_preferences": item.override_preferences,
            "warnings": preference_warnings(item.event, trip.preferences),
        }
        if item.day_id:
            days[item.day.position]["items"].append(payload)
        else:
            unscheduled.append(payload)
    return {
        "id": trip.pk,
        "revision": trip.revision,
        "is_archived": trip.is_archived,
        "name": trip.name,
        "start_date": trip.start_date.isoformat(),
        "duration": trip.duration,
        "preferences": trip.preferences,
        "days": days,
        "unscheduled": unscheduled,
    }


@transaction.atomic
def save_document(user, raw, *, trip=None, confirmed=False):
    from .models import Trip, TripDay, TripActivity

    data = validate_document(raw, allow_historical=trip is not None)
    if trip:
        trip = Trip.objects.select_for_update().get(pk=trip.pk, user=user)
        if trip.is_archived:
            raise serializers.ValidationError(
                {"archived": "Restore this trip before editing it."}
            )
        revision = serializers.IntegerField(min_value=1).run_validation(
            raw.get("revision")
        )
        if revision != trip.revision:
            raise serializers.ValidationError(
                {"conflict": "This trip changed in another tab. Reload before saving."},
                code="conflict",
            )
        previous = trip_document(trip)
        removed = _keys(previous) - _keys(data)
        if removed and not confirmed:
            raise serializers.ValidationError(
                {"confirmation": "Confirm removal or regeneration before saving."}
            )
        trip.revision += 1
    else:
        trip = Trip(user=user)
    for field in ("name", "start_date", "duration", "preferences"):
        setattr(trip, field, data[field])
    trip.save()
    trip.refresh_from_db()
    # Reconciliation is atomic; the revision protects against lost updates.
    trip.activities.all().delete()
    trip.days.all().delete()
    for position, day in enumerate(data["days"]):
        saved_day = TripDay.objects.create(
            trip=trip, position=position, date=day["date"]
        )
        for order, item in enumerate(day["items"]):
            TripActivity.objects.create(
                trip=trip,
                day=saved_day,
                key=item["key"],
                event_id=item["event_id"],
                slot_type=item["slot_type"],
                locked=item["locked"],
                source=item["source"],
                position=order,
                override_preferences=item["override_preferences"],
            )
    for order, item in enumerate(data["unscheduled"]):
        TripActivity.objects.create(
            trip=trip,
            key=item["key"],
            event_id=item["event_id"],
            slot_type=item["slot_type"],
            locked=item["locked"],
            source=item["source"],
            position=order,
            override_preferences=item["override_preferences"],
        )
    return trip
