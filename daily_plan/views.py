from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import DailyPlan, DailyPlanItem
from .serializers import (
    DailyPlanSerializer,
    EventIDField,
    _ordered_events_from_legacy_m2m,
)
from .services import (
    build_plan_items_from_ordered_events,
    generate_multiday_plan,
    generate_recommendations,
)
from accounts.models import UserPreferences
from events.models import Event
import logging

logger = logging.getLogger(__name__)


def _ordered_plan_items(plan):
    return list(plan.items.select_related("event").order_by("order", "id"))


def _sync_legacy_events_from_items(plan):
    ordered_items = _ordered_plan_items(plan)
    plan.events.set([item.event for item in ordered_items])
    return ordered_items


def _ensure_legacy_plan_items(plan):
    if not plan.items.exists():
        specs = build_plan_items_from_ordered_events(
            _ordered_events_from_legacy_m2m(plan)
        )
        DailyPlanItem.objects.bulk_create(
            [
                DailyPlanItem(
                    plan=plan,
                    event=spec["event"],
                    slot_type=spec["slot_type"],
                    order=spec["order"],
                    source="manual",
                    locked=False,
                )
                for spec in specs
            ]
        )


def _serialize_plan_with_count(plan):
    payload = DailyPlanSerializer(plan).data
    payload["count"] = len(payload.get("events", []))
    return payload


@transaction.atomic
def _persist_generated_plan_items(plan, ordered_events):
    plan = DailyPlan.objects.select_for_update().get(pk=plan.pk)
    if any(not event.is_available_on(plan.date) for event in ordered_events):
        raise ValueError("A recommended event is unavailable on the assigned day.")
    locked_items = list(
        plan.items.filter(locked=True).select_related("event").order_by("order", "id")
    )
    if any(not item.event.is_available_on(plan.date) for item in locked_items):
        raise ValueError(
            "A locked event is unavailable on this date. Remove or replace it before regenerating."
        )
    locked_positions = {(item.slot_type, item.order) for item in locked_items}
    locked_event_ids = {item.event_id for item in locked_items}

    if not ordered_events and (plan.items.exists() or plan.events.exists()):
        # A partial multi-day result must not clear an existing day's choices.
        return

    plan.items.filter(locked=False).delete()
    item_specs = build_plan_items_from_ordered_events(
        ordered_events, source="generated", locked=False
    )

    new_items = []
    for spec in item_specs:
        if spec["event_id"] in locked_event_ids:
            continue
        if (spec["slot_type"], spec["order"]) in locked_positions:
            continue
        new_items.append(
            DailyPlanItem(
                plan=plan,
                event=spec["event"],
                slot_type=spec["slot_type"],
                order=spec["order"],
                source=spec["source"],
                locked=spec["locked"],
            )
        )

    if new_items:
        DailyPlanItem.objects.bulk_create(new_items)

    _sync_legacy_events_from_items(plan)
    return _ordered_plan_items(plan)


def _next_plan_item_order(plan):
    current_max = plan.items.aggregate(max_order=Max("order")).get("max_order")
    return 0 if current_max is None else int(current_max) + 1


def _parse_iso_date(value, field_name):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name} format. Expected YYYY-MM-DD") from exc


def _parse_trip_duration(raw_value):
    if raw_value is None or raw_value == "":
        return None
    if isinstance(raw_value, (bool, float)):
        raise ValueError("trip_duration must be an integer between 1 and 30.")
    try:
        trip_duration = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("trip_duration must be an integer between 1 and 30.") from exc
    if trip_duration < 1 or trip_duration > 30:
        raise ValueError("trip_duration must be an integer between 1 and 30.")
    return trip_duration


def _resolve_date_range(start_date_str=None, end_date_str=None, trip_duration=None):
    if not start_date_str:
        raise ValueError("start_date is required. Format: YYYY-MM-DD")

    start_date = _parse_iso_date(start_date_str, "start_date")
    end_date = (
        _parse_iso_date(end_date_str, "end_date")
        if end_date_str not in (None, "")
        else None
    )

    if start_date < date.today():
        raise ValueError("Cannot create plans for past dates.")
    if end_date and end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")

    resolved_trip_duration = _parse_trip_duration(trip_duration)
    if end_date:
        derived_duration = (end_date - start_date).days + 1
        if (
            resolved_trip_duration is not None
            and resolved_trip_duration != derived_duration
        ):
            raise ValueError(
                "trip_duration must match the provided start_date and end_date range."
            )
        resolved_trip_duration = _parse_trip_duration(derived_duration)

    return start_date, end_date, resolved_trip_duration


def _parse_exclude_plan_dates(raw_value):
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError("exclude_plan_dates must be a list of YYYY-MM-DD dates.")

    parsed_dates = []
    for day_str in raw_value:
        try:
            parsed_dates.append(_parse_iso_date(day_str, "exclude_plan_dates"))
        except ValueError as exc:
            raise ValueError(
                "exclude_plan_dates must only contain YYYY-MM-DD dates."
            ) from exc
    return parsed_dates


def _resolve_request_or_preference_dates(
    user, date_str=None, start_date_str=None, end_date_str=None
):
    if date_str or start_date_str or end_date_str:
        return date_str, start_date_str, end_date_str

    preferences = UserPreferences.objects.filter(user=user).first()
    if not preferences or not preferences.start_date:
        return date_str, start_date_str, end_date_str

    return (
        preferences.start_date.isoformat(),
        preferences.start_date.isoformat(),
        preferences.end_date.isoformat() if preferences.end_date else None,
    )


def _has_required_planning_preferences(user):
    preferences = UserPreferences.objects.filter(user=user).first()
    if not preferences:
        return False

    interests = [value for value in (preferences.interests or []) if value]
    return bool(interests)


class DailyPlanListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = DailyPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            DailyPlan.objects.filter(user=self.request.user)
            .prefetch_related("events", "items__event")
            .order_by("-date")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_date = serializer.validated_data.get("date")
        if DailyPlan.objects.filter(user=request.user, date=plan_date).exists():
            return Response(
                {"date": "Plan already exists for this date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {"date": "Plan already exists for this date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class DailyPlanRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DailyPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DailyPlan.objects.filter(user=self.request.user).prefetch_related(
            "events",
            "items__event",
        )


class DailyPlanEventRemoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk, event_id):
        daily_plan = get_object_or_404(
            DailyPlan.objects.select_for_update().prefetch_related(
                "events", "items__event"
            ),
            pk=pk,
            user=request.user,
        )

        matching_items = list(daily_plan.items.filter(event_id=event_id))
        if not matching_items and not daily_plan.events.filter(pk=event_id).exists():
            return Response(
                {"detail": "Event is not part of this plan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if matching_items:
            daily_plan.items.filter(event_id=event_id).delete()
            _sync_legacy_events_from_items(daily_plan)
        else:
            daily_plan.events.remove(event_id)
        return Response(
            _serialize_plan_with_count(daily_plan), status=status.HTTP_200_OK
        )


class DailyPlanItemListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        daily_plan = get_object_or_404(
            DailyPlan.objects.select_for_update().prefetch_related(
                "items__event", "events"
            ),
            pk=pk,
            user=request.user,
        )

        event_id = EventIDField().run_validation(request.data.get("event_id"))
        slot_type = request.data.get("slot_type") or "activity"
        if slot_type not in {choice for choice, _ in DailyPlanItem.SLOT_CHOICES}:
            return Response(
                {"slot_type": "Invalid slot type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return Response(
                {"event_id": "Event not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not event.is_available_on(daily_plan.date):
            return Response(
                {"event_id": f"Event {event.id} is not available on {daily_plan.date}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if daily_plan.items.filter(event=event).exists():
            return Response(
                {"detail": "Event is already part of this plan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _ensure_legacy_plan_items(daily_plan)
        if daily_plan.items.filter(event=event).exists():
            return Response(
                {"detail": "Event is already part of this plan."}, status=400
            )
        DailyPlanItem.objects.create(
            plan=daily_plan,
            event=event,
            slot_type=slot_type,
            order=_next_plan_item_order(daily_plan),
            source="manual",
            locked=serializers.BooleanField().run_validation(
                request.data.get("locked", False)
            ),
        )
        _sync_legacy_events_from_items(daily_plan)
        return Response(
            _serialize_plan_with_count(daily_plan), status=status.HTTP_201_CREATED
        )


class DailyPlanItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk, item_id):
        daily_plan = get_object_or_404(
            DailyPlan.objects.select_for_update().prefetch_related(
                "items__event", "events"
            ),
            pk=pk,
            user=request.user,
        )
        item = get_object_or_404(daily_plan.items.select_related("event"), pk=item_id)

        if "event_id" in request.data:
            event_id = EventIDField().run_validation(request.data.get("event_id"))
            try:
                event = Event.objects.get(pk=event_id)
            except Event.DoesNotExist:
                return Response(
                    {"event_id": "Event not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not event.is_available_on(daily_plan.date):
                return Response(
                    {
                        "event_id": f"Event {event.id} is not available on {daily_plan.date}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                event.id != item.event_id
                and daily_plan.items.filter(event_id=event.id)
                .exclude(pk=item.pk)
                .exists()
            ):
                return Response(
                    {"detail": "Event is already part of this plan."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            item.event = event
            item.source = "replacement"

        if "locked" in request.data:
            item.locked = serializers.BooleanField().run_validation(
                request.data.get("locked")
            )

        item.save(update_fields=["event", "source", "locked", "updated_at"])
        _sync_legacy_events_from_items(daily_plan)
        return Response(
            _serialize_plan_with_count(daily_plan), status=status.HTTP_200_OK
        )

    @transaction.atomic
    def delete(self, request, pk, item_id):
        daily_plan = get_object_or_404(
            DailyPlan.objects.select_for_update().prefetch_related(
                "items__event", "events"
            ),
            pk=pk,
            user=request.user,
        )
        item = get_object_or_404(daily_plan.items.select_related("event"), pk=item_id)
        item.delete()
        _sync_legacy_events_from_items(daily_plan)
        return Response(
            _serialize_plan_with_count(daily_plan), status=status.HTTP_200_OK
        )


class DailyPlanAddAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        event_id = EventIDField().run_validation(request.data.get("event_id"))
        locked = serializers.BooleanField().run_validation(
            request.data.get("locked", False)
        )
        date_str = request.data.get("date")
        slot_type = request.data.get("slot_type") or "activity"

        if event_id is None:
            return Response(
                {"event_id": "event_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if slot_type not in {choice for choice, _ in DailyPlanItem.SLOT_CHOICES}:
            return Response(
                {"slot_type": "Invalid slot type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_str in (None, ""):
            return Response(
                {"date": "date is required. Format: YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            plan_date = _parse_iso_date(date_str, "date")
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if plan_date < date.today():
            return Response(
                {"detail": "Cannot create plans for past dates."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            return Response(
                {"event_id": "Event not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not event.occurs_on(plan_date):
            return Response(
                {"event_id": f"Event {event.id} is not available on {plan_date}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        daily_plan, _ = DailyPlan.objects.get_or_create(
            user=request.user,
            date=plan_date,
        )
        daily_plan = DailyPlan.objects.select_for_update().get(pk=daily_plan.pk)

        if (
            daily_plan.items.filter(event=event).exists()
            or daily_plan.events.filter(pk=event.pk).exists()
        ):
            return Response(
                _serialize_plan_with_count(daily_plan),
                status=status.HTTP_200_OK,
            )

        _ensure_legacy_plan_items(daily_plan)
        DailyPlanItem.objects.create(
            plan=daily_plan,
            event=event,
            slot_type=slot_type,
            order=_next_plan_item_order(daily_plan),
            source="manual",
            locked=locked,
        )
        _sync_legacy_events_from_items(daily_plan)
        return Response(
            _serialize_plan_with_count(daily_plan),
            status=status.HTTP_201_CREATED,
        )


class GenerateDailyPlanAPIView(APIView):
    """
    Generate a personalized daily plan based on user preferences.

    Request body:
        { "date": "2026-03-15" }

    Response:
        { "id": 1, "date": "2026-03-15", "events": [...], "count": 3 }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not _has_required_planning_preferences(user):
            return Response(
                {"detail": "Please set your preferences first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_str, start_date_str, end_date_str = _resolve_request_or_preference_dates(
            user,
            date_str=request.data.get("date"),
            start_date_str=request.data.get("start_date"),
            end_date_str=request.data.get("end_date"),
        )
        start_date_str = start_date_str or date_str
        seed = request.data.get("seed")
        exclude_plan_dates = request.data.get("exclude_plan_dates")

        if not date_str and not start_date_str:
            return Response(
                {"detail": "Date is required. Format: YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resolved_start_date, resolved_end_date, _ = _resolve_date_range(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                trip_duration=request.data.get("trip_duration"),
            )
            plan_date = _parse_iso_date(date_str or start_date_str, "date")
            if plan_date < date.today():
                raise ValueError("Cannot create plans for past dates.")
            if plan_date < resolved_start_date or (
                resolved_end_date and plan_date > resolved_end_date
            ):
                raise ValueError("date must be within the selected trip range.")
            valid_exclude_dates = _parse_exclude_plan_dates(exclude_plan_dates)
        except ValueError as exc:
            logger.warning("Invalid date format from user %s: %s", user.id, date_str)
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exclude_ids = set()
        if valid_exclude_dates:
            sibling_plans = DailyPlan.objects.filter(
                user=user,
                date__in=valid_exclude_dates,
            ).prefetch_related("events")
            for plan in sibling_plans:
                exclude_ids.update(plan.events.values_list("id", flat=True))

        try:
            recommended_events = generate_recommendations(
                user,
                date_str=plan_date.isoformat(),
                seed=seed,
                exclude_ids=exclude_ids,
            )
        except Exception as e:
            logger.error(
                "Unexpected error generating plan for user %s: %s",
                user.id,
                e,
                exc_info=True,
            )
            return Response(
                {"detail": "Unexpected error while generating plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if recommended_events is None:
            return Response(
                {"detail": "Please set your preferences first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not recommended_events:
            return Response(
                {"detail": "No recommendations found for your interests and budget."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                daily_plan, created = DailyPlan.objects.get_or_create(
                    user=user,
                    date=plan_date,
                )
                _persist_generated_plan_items(daily_plan, recommended_events)

            action = "created" if created else "updated"
            logger.info("Daily plan %s for user %s on %s", action, user.id, plan_date)

            return Response(
                _serialize_plan_with_count(daily_plan),
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                "Error saving daily plan for user %s: %s", user.id, e, exc_info=True
            )
            return Response(
                {"detail": "Error saving daily plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GenerateMultiDayPlanAPIView(APIView):
    """Generate and persist a full multi-day itinerary in one request."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not _has_required_planning_preferences(user):
            return Response(
                {"detail": "Please set your preferences first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _, start_date_str, end_date_str = _resolve_request_or_preference_dates(
            user,
            start_date_str=request.data.get("start_date")
            or request.data.get("date_from"),
            end_date_str=request.data.get("end_date") or request.data.get("date_to"),
        )
        trip_duration = request.data.get("trip_duration")

        if not start_date_str:
            return Response(
                {"detail": "start_date is required. Format: YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_date, end_date, trip_duration = _resolve_date_range(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                trip_duration=trip_duration,
            )
        except ValueError as exc:
            logger.warning(
                "Invalid multi-day input from user %s: start_date=%s end_date=%s trip_duration=%s",
                user.id,
                start_date_str,
                end_date_str,
                request.data.get("trip_duration"),
            )
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            generated_days = generate_multiday_plan(
                user,
                start_date_str,
                trip_duration=trip_duration,
                end_date_str=end_date_str,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(
                "Unexpected error generating multi-day plan for user %s: %s",
                user.id,
                e,
                exc_info=True,
            )
            return Response(
                {"detail": "Unexpected error while generating plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if generated_days is None:
            return Response(
                {"detail": "Please set your preferences first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_events = sum(len(events or []) for _, events in generated_days)
        if total_events == 0:
            return Response(
                {"detail": "No recommendations found for your interests and budget."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            generated_dates = [
                date.fromisoformat(day_date_str) for day_date_str, _ in generated_days
            ]

            with transaction.atomic():
                existing_qs = DailyPlan.objects.filter(
                    user=user,
                    date__in=generated_dates,
                ).prefetch_related("items__event")
                had_existing = existing_qs.exists()

                plans_payload = []
                for day_date_str, events in generated_days:
                    day_date = date.fromisoformat(day_date_str)
                    daily_plan, _ = DailyPlan.objects.get_or_create(
                        user=user, date=day_date
                    )
                    _persist_generated_plan_items(daily_plan, events)
                    plans_payload.append(_serialize_plan_with_count(daily_plan))

            return Response(
                {
                    "trip_duration": len(generated_days),
                    "start_date": start_date.isoformat(),
                    "end_date": (
                        generated_days[-1][0] if generated_days else start_date_str
                    ),
                    "plans": plans_payload,
                    "total_events": total_events,
                },
                status=status.HTTP_200_OK if had_existing else status.HTTP_201_CREATED,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(
                "Error saving multi-day plan for user %s: %s", user.id, e, exc_info=True
            )
            return Response(
                {"detail": "Error saving daily plan."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
