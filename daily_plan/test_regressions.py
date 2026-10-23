from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserPreferences
from daily_plan.models import DailyPlan, DailyPlanItem
from daily_plan.serializers import DailyPlanSerializer
from daily_plan.services import generate_multiday_plan, generate_recommendations
from events.models import Event


class PlanningRegressionTests(TestCase):
    def setUp(self):
        Event.objects.all().delete()
        self.user = get_user_model().objects.create_user(username="planner")
        self.preferences = UserPreferences.objects.create(
            user=self.user, interests=["nature", "events"], trip_duration=2
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.day = timezone.localdate() + timedelta(days=3)
        self.event = self.place("Evergreen Park")

    def place(self, title, **kwargs):
        data = dict(
            category="nature",
            date=timezone.now(),
            rating="4.8",
            price="20.00",
            description="A visitor attraction",
            tourism_relevance=5,
            latitude=24.7136,
            longitude=46.6753,
            location="Riyadh",
        )
        data.update(kwargs)
        return Event.objects.create(title=title, **data)

    def at(self, day):
        return timezone.make_aware(datetime.combine(day, time(12)))

    def plan(self):
        plan = DailyPlan.objects.create(user=self.user, date=self.day)
        plan.events.add(self.event)
        DailyPlanItem.objects.create(
            plan=plan, event=self.event, slot_type="activity", locked=True
        )
        return plan

    def test_assigned_day_never_includes_later_event_from_trip_window(self):
        later = self.place(
            "Later Festival",
            category="events",
            start_date=self.at(self.day + timedelta(days=1)),
            end_date=self.at(self.day + timedelta(days=1)),
        )
        events = generate_recommendations(
            self.user,
            date_str=str(self.day),
            start_date_str=str(self.day),
            end_date_str=str(self.day + timedelta(days=1)),
        )
        self.assertTrue(events)
        self.assertNotIn(later, events)
        self.assertTrue(all(event.is_available_on(self.day) for event in events))

    def test_multiday_checks_each_assigned_day_and_preserves_uniqueness(self):
        later = self.place(
            "Second Day Festival",
            category="events",
            date=self.at(self.day + timedelta(days=1)),
        )
        days = generate_multiday_plan(
            self.user, str(self.day), end_date_str=str(self.day + timedelta(days=1))
        )
        ids = []
        for day, events in days:
            assigned = self.day.fromisoformat(day)
            self.assertTrue(all(event.is_available_on(assigned) for event in events))
            ids.extend(event.id for event in events)
        self.assertNotIn(later, days[0][1])
        self.assertIn(later, days[1][1])
        self.assertEqual(len(ids), len(set(ids)))

    def test_start_date_without_end_date_is_a_single_day_event(self):
        expired = self.place(
            "Expired Festival",
            category="events",
            start_date=self.at(self.day - timedelta(days=1)),
        )
        self.assertNotIn(
            expired, generate_recommendations(self.user, date_str=str(self.day))
        )

    def test_unavailable_locked_item_blocks_regeneration_without_losing_plan(self):
        plan = self.plan()
        item_id = plan.items.get().pk
        self.event.is_active = False
        self.event.save()
        self.place("Available Park")
        for url, payload in [
            ("/api/daily-plan/generate/", {"date": str(self.day)}),
            (
                "/api/daily-plan/generate-multiday/",
                {"start_date": str(self.day), "trip_duration": 2},
            ),
        ]:
            response = self.client.post(url, payload, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("locked event", response.data["detail"])
            self.assertEqual(plan.items.get().pk, item_id)
            self.assertEqual(list(plan.events.all()), [self.event])
            self.assertEqual(DailyPlan.objects.count(), 1)

    def test_budget_and_rating_are_not_relaxed_when_no_matches_exist(self):
        self.event.price = 200
        self.event.save()
        self.preferences.budget_max = 50
        self.preferences.save()
        self.assertEqual(
            generate_recommendations(self.user, date_str=str(self.day)), []
        )
        self.event.price = 20
        self.event.rating = "4.0"
        self.event.save()
        self.preferences.min_rating = "4.5"
        self.preferences.save()
        self.assertEqual(
            generate_recommendations(self.user, date_str=str(self.day)), []
        )
        response = self.client.post(
            "/api/daily-plan/generate/", {"date": str(self.day)}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(DailyPlan.objects.exists())

    def test_supporting_suggestions_respect_explicit_constraints(self):
        self.preferences.budget_min = 10
        self.preferences.budget_max = 30
        self.preferences.min_rating = "4.5"
        self.preferences.save()
        self.place("Expensive Cafe", category="food", price=200)
        self.place("Low Rating Cafe", category="food", rating="4.0")
        self.place("Free Attraction", price=0)
        events = generate_recommendations(self.user, date_str=str(self.day))
        self.assertTrue(events)
        self.assertTrue(
            all(10 <= event.price <= 30 and event.rating >= 4.5 for event in events)
        )

    def test_invalid_ids_are_400_across_plan_and_item_endpoints(self):
        plan = self.plan()
        item = plan.items.get()
        for invalid in ["invalid", None, True, 1.2, -1, {}, 10**30]:
            with self.subTest(invalid=invalid):
                payload = {"event_id": invalid, "date": str(self.day)}
                for url in [
                    "/api/daily-plan/add/",
                    f"/api/daily-plan/{plan.pk}/items/",
                ]:
                    self.assertEqual(
                        self.client.post(url, payload, format="json").status_code, 400
                    )
                self.assertEqual(
                    self.client.patch(
                        f"/api/daily-plan/{plan.pk}/items/{item.pk}/",
                        {"event_id": invalid},
                        format="json",
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    self.client.patch(
                        f"/api/daily-plan/{plan.pk}/",
                        {"events": [invalid]},
                        format="json",
                    ).status_code,
                    400,
                )
        self.assertEqual(plan.items.get().event_id, self.event.pk)

    def test_nonexistent_ids_are_rejected_without_partial_save(self):
        response = self.client.post(
            "/api/daily-plan/",
            {"date": str(self.day), "events": [self.event.pk, 999999]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DailyPlan.objects.exists())

    def test_duplicate_event_ids_rejected_and_existing_items_preserved(self):
        plan = self.plan()
        item_id = plan.items.get().pk
        response = self.client.patch(
            f"/api/daily-plan/{plan.pk}/",
            {"events": [self.event.pk, self.event.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(plan.items.get().pk, item_id)
        self.assertEqual(list(plan.events.all()), [self.event])

    def test_events_must_be_a_list(self):
        for invalid in [None, "1", {"id": self.event.pk}]:
            response = self.client.post(
                "/api/daily-plan/",
                {"date": str(self.day), "events": invalid},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(DailyPlan.objects.exists())

    def test_serializer_update_rolls_back_deletion_when_item_write_fails(self):
        plan = self.plan()
        before = plan.items.get().pk
        other = self.place("Another Park")
        serializer = DailyPlanSerializer(
            plan, data={"events": [other.pk]}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch(
            "daily_plan.serializers.DailyPlanItem.objects.bulk_create",
            side_effect=IntegrityError("injected"),
        ):
            with self.assertRaises(IntegrityError):
                serializer.save()
        self.assertEqual(plan.items.get().pk, before)
        self.assertEqual(list(plan.events.all()), [self.event])

    def test_generated_plan_creation_rolls_back_on_item_failure(self):
        with patch(
            "daily_plan.views.DailyPlanItem.objects.bulk_create",
            side_effect=IntegrityError("injected"),
        ):
            response = self.client.post(
                "/api/daily-plan/generate/", {"date": str(self.day)}, format="json"
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(DailyPlan.objects.exists())

    def test_date_only_update_validates_existing_event_availability(self):
        plan = self.plan()
        self.event.category = "events"
        self.event.date = self.at(self.day)
        self.event.save()
        response = self.client.patch(
            f"/api/daily-plan/{plan.pk}/",
            {"date": str(self.day + timedelta(days=1))},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.date, self.day)
        self.assertTrue(plan.items.get().locked)

    def test_date_only_update_preserves_item_identity_and_lock(self):
        plan = self.plan()
        item_id = plan.items.get().pk
        response = self.client.patch(
            f"/api/daily-plan/{plan.pk}/",
            {"date": str(self.day + timedelta(days=1))},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(plan.items.get().pk, item_id)
        self.assertTrue(plan.items.get().locked)

    def test_move_to_existing_plan_date_returns_400(self):
        plan = self.plan()
        DailyPlan.objects.create(user=self.user, date=self.day + timedelta(days=1))
        response = self.client.patch(
            f"/api/daily-plan/{plan.pk}/",
            {"date": str(self.day + timedelta(days=1))},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_range_over_thirty_days_rejected_in_apis_service_and_preferences(self):
        end = self.day + timedelta(days=30)
        payload = {"start_date": str(self.day), "end_date": str(end)}
        for url in [
            "/api/daily-plan/generate/",
            "/api/daily-plan/generate-multiday/",
            "/api/auth/preferences/",
        ]:
            response = self.client.post(url, payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        with self.assertRaises(ValueError):
            generate_multiday_plan(self.user, str(self.day), end_date_str=str(end))
        self.assertFalse(DailyPlan.objects.exists())

    def test_thirty_day_boundary_accepted_and_noninteger_duration_rejected(self):
        days = generate_multiday_plan(
            self.user, str(self.day), end_date_str=str(self.day + timedelta(days=29))
        )
        self.assertEqual(len(days), 30)
        for duration in [True, 1.5, 0, 31]:
            response = self.client.post(
                "/api/daily-plan/generate-multiday/",
                {"start_date": str(self.day), "trip_duration": duration},
                format="json",
            )
            self.assertEqual(response.status_code, 400)

    def test_preferences_validate_rating_and_synchronize_duration(self):
        for rating in [-1, 5.1]:
            response = self.client.post(
                "/api/auth/preferences/", {"min_rating": rating}, format="json"
            )
            self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/auth/preferences/",
            {
                "start_date": str(self.day),
                "end_date": str(self.day + timedelta(days=2)),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.trip_duration, 3)

    def test_language_can_be_saved_after_previous_trip_has_ended(self):
        self.preferences.start_date = self.day - timedelta(days=10)
        self.preferences.end_date = self.day - timedelta(days=9)
        self.preferences.save()
        response = self.client.put(
            "/api/auth/preferences/", {"preferred_language": "ar"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.preferences.refresh_from_db()
        self.assertEqual(self.preferences.preferred_language, "ar")

    def test_string_false_lock_does_not_lock_item(self):
        response = self.client.post(
            "/api/daily-plan/add/",
            {"date": str(self.day), "event_id": self.event.pk, "locked": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(DailyPlanItem.objects.get().locked)

    def test_manual_add_rolls_back_if_legacy_sync_fails(self):
        with patch(
            "daily_plan.views._sync_legacy_events_from_items",
            side_effect=RuntimeError("injected"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/api/daily-plan/add/",
                    {"date": str(self.day), "event_id": self.event.pk},
                    format="json",
                )
        self.assertFalse(DailyPlan.objects.exists())

    def test_adding_to_legacy_plan_preserves_its_existing_events(self):
        plan = DailyPlan.objects.create(user=self.user, date=self.day)
        plan.events.add(self.event)
        other = self.place("Additional Park")
        response = self.client.post(
            "/api/daily-plan/add/",
            {"date": str(self.day), "event_id": other.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertSetEqual(
            set(plan.events.values_list("pk", flat=True)), {self.event.pk, other.pk}
        )
        self.assertEqual(plan.items.count(), 2)

    def test_readding_legacy_event_is_idempotent_and_preserves_events(self):
        plan = DailyPlan.objects.create(user=self.user, date=self.day)
        plan.events.add(self.event)
        response = self.client.post(
            "/api/daily-plan/add/",
            {"date": str(self.day), "event_id": self.event.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(plan.events.all()), [self.event])
