from copy import deepcopy
from datetime import timedelta
from importlib import import_module
import shutil
import subprocess

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from events.models import Event, Favorite
from .models import Trip, DailyPlan, DailyPlanItem


class TripProductTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("trip-owner")
        cls.other = User.objects.create_user(
            "other-owner", is_staff=True, is_superuser=True
        )
        cls.date = timezone.localdate() + timedelta(days=20)
        cls.events = [
            Event.objects.create(
                title=f"Synthetic Heritage Experience {i}",
                category="heritage",
                description="Synthetic historical attraction for isolated tests",
                date=timezone.now(),
                location="Riyadh",
                latitude=24.7 + i / 1000,
                longitude=46.7,
                rating=4.5,
                price=20,
            )
            for i in range(20)
        ]
        Event.objects.exclude(pk__in=[event.pk for event in cls.events]).update(
            is_active=False
        )

    def setUp(self):
        self.client = APIClient()
        self.raw = {
            "name": "Family visit",
            "start_date": self.date.isoformat(),
            "duration": 2,
            "preferences": {
                "interests": ["heritage"],
                "budget_max": 50,
                "min_rating": 4,
            },
            "days": [{"items": []}, {"items": []}],
            "unscheduled": [],
        }

    def preview(self, **payload):
        return self.client.post(
            "/api/trips/preview/", {"trip": self.raw, **payload}, format="json"
        )

    def save_trip(self, raw=None):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/trips/", raw or self.raw, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def item(self, event=None, locked=False, key="one", **extra):
        return {
            "key": key,
            "event_id": (event or self.events[0]).pk,
            "slot_type": "activity",
            "locked": locked,
            **extra,
        }

    def test_guest_can_preview_without_account_or_database_writes(self):
        before = (User.objects.count(), Trip.objects.count(), DailyPlan.objects.count())
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["trip"]["days"][0]["items"])
        ids = [
            item["event_id"]
            for day in response.data["trip"]["days"]
            for item in day["items"]
        ]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            before,
            (User.objects.count(), Trip.objects.count(), DailyPlan.objects.count()),
        )

    def test_guest_save_requires_authentication(self):
        self.assertEqual(
            self.client.post("/api/trips/", self.raw, format="json").status_code, 401
        )

    def test_empty_legacy_generation_preserves_existing_unlocked_selections(self):
        from .views import _persist_generated_plan_items

        plan = DailyPlan.objects.create(user=self.user, date=self.date)
        item = DailyPlanItem.objects.create(
            plan=plan, event=self.events[0], slot_type="activity", locked=False
        )
        plan.events.add(self.events[0])
        _persist_generated_plan_items(plan, [])
        self.assertTrue(plan.items.filter(pk=item.pk).exists())
        self.assertEqual(
            list(plan.events.values_list("pk", flat=True)), [self.events[0].pk]
        )

    def test_overlapping_named_trips_are_independent(self):
        first = self.save_trip()
        self.raw["name"] = "Another visit"
        second = self.save_trip()
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["start_date"], second["start_date"])
        self.assertEqual(Trip.objects.filter(user=self.user).count(), 2)

    def test_private_trips_cannot_be_read_or_changed_by_other_user_or_superuser(self):
        saved = self.save_trip()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/trips/{saved["id"]}/').status_code, 404)
        self.assertEqual(
            self.client.put(
                f'/api/trips/{saved["id"]}/', saved, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get("/api/trips/").data, [])

    def test_revision_rejects_stale_update_without_losing_data(self):
        saved = self.save_trip()
        updated = {**saved, "name": "Updated"}
        first = self.client.put(f'/api/trips/{saved["id"]}/', updated, format="json")
        self.assertEqual(first.status_code, 200)
        second = self.client.put(f'/api/trips/{saved["id"]}/', saved, format="json")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Trip.objects.get(pk=saved["id"]).name, "Updated")

    def test_archive_requires_confirmation_and_preserves_every_selection(self):
        self.raw["days"][0]["items"] = [self.item(locked=True)]
        self.raw["unscheduled"] = [
            self.item(event=self.events[1], key="later", locked=True)
        ]
        saved = self.save_trip()
        url = f'/api/trips/{saved["id"]}/'
        self.assertEqual(
            self.client.delete(
                url, {"revision": saved["revision"]}, format="json"
            ).status_code,
            400,
        )
        response = self.client.delete(
            url, {"revision": saved["revision"], "confirmed": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        trip = Trip.objects.get(pk=saved["id"])
        self.assertTrue(trip.is_archived)
        self.assertEqual(trip.activities.count(), 2)
        self.assertEqual(trip.activities.filter(locked=True).count(), 2)
        self.assertEqual(trip.days.count(), 2)
        self.assertEqual(self.client.get("/api/trips/").data, [])
        self.assertEqual(
            self.client.get("/api/trips/?archived=1").data[0]["id"], trip.pk
        )

    def test_archive_restore_and_revision_conflicts_are_safe(self):
        saved = self.save_trip()
        url = f'/api/trips/{saved["id"]}/'
        archived = self.client.delete(
            url, {"revision": saved["revision"], "confirmed": True}, format="json"
        ).data
        self.assertEqual(self.client.put(url, saved, format="json").status_code, 400)
        stale = self.client.patch(
            url,
            {"action": "restore", "revision": saved["revision"], "confirmed": True},
            format="json",
        )
        self.assertEqual(stale.status_code, 409)
        restored = self.client.patch(
            url,
            {"action": "restore", "revision": archived["revision"], "confirmed": True},
            format="json",
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertFalse(restored.data["is_archived"])
        self.assertEqual(self.client.get("/api/trips/").data[0]["id"], saved["id"])

    def test_another_user_including_superuser_cannot_archive_or_restore_a_trip(self):
        saved = self.save_trip()
        self.client.force_authenticate(self.other)
        url = f'/api/trips/{saved["id"]}/'
        payload = {
            "confirmed": True,
            "revision": saved["revision"],
            "action": "restore",
        }
        self.assertEqual(
            self.client.delete(url, payload, format="json").status_code, 404
        )
        self.assertEqual(
            self.client.patch(url, payload, format="json").status_code, 404
        )
        self.assertFalse(Trip.objects.get(pk=saved["id"]).is_archived)

    def test_guest_cannot_archive_or_restore_and_unknown_actions_are_rejected(self):
        saved = self.save_trip()
        url = f'/api/trips/{saved["id"]}/'
        self.assertEqual(
            self.client.patch(url, {"action": "delete"}, format="json").status_code, 400
        )
        self.client.force_authenticate(None)
        self.assertEqual(self.client.delete(url, {}, format="json").status_code, 401)
        self.assertEqual(
            self.client.patch(url, {"action": "restore"}, format="json").status_code,
            401,
        )

    def test_removal_requires_confirmation(self):
        self.raw["days"][0]["items"] = [self.item(locked=True)]
        saved = self.save_trip()
        saved["days"][0]["items"] = []
        url = f'/api/trips/{saved["id"]}/'
        self.assertEqual(self.client.put(url, saved, format="json").status_code, 400)
        self.assertEqual(Trip.objects.get(pk=saved["id"]).activities.count(), 1)
        self.assertEqual(
            self.client.put(
                url, {**saved, "confirmed": True}, format="json"
            ).status_code,
            200,
        )

    def test_duration_reduction_previews_and_preserves_locked_unscheduled_places(self):
        self.raw["days"][1]["items"] = [self.item(locked=True)]
        response = self.preview(
            action="dates", start_date=self.date.isoformat(), duration=1
        )
        self.assertTrue(response.data["requires_confirmation"])
        self.assertEqual(len(self.raw["days"]), 2)
        response = self.preview(
            action="dates", start_date=self.date.isoformat(), duration=1, confirmed=True
        )
        self.assertEqual(response.status_code, 200, response.data)
        trip = response.data["trip"]
        self.assertEqual(trip["duration"], 1)
        self.assertTrue(trip["unscheduled"][0]["locked"])
        self.assertEqual(trip["unscheduled"][0]["key"], "one")

    def test_date_shift_preserves_suitable_places_and_previews_unavailable_events(self):
        event = Event.objects.create(
            title="Synthetic date-only event",
            category="events",
            date=timezone.make_aware(
                timezone.datetime.combine(self.date, timezone.datetime.min.time())
            ),
            rating=4.5,
        )
        self.raw["days"][0]["items"] = [
            self.item(event=event),
            self.item(event=self.events[0], key="evergreen"),
        ]
        response = self.preview(
            action="dates",
            start_date=(self.date + timedelta(days=3)).isoformat(),
            duration=2,
            confirmed=True,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["trip"]["days"][0]["items"][0]["key"], "evergreen"
        )
        self.assertEqual(response.data["trip"]["unscheduled"][0]["event_id"], event.pk)

    def test_regenerate_day_excludes_other_days_and_preserves_locked_activity(self):
        self.raw = self.preview().data["trip"]
        self.raw["days"][0]["items"][0]["locked"] = True
        locked = deepcopy(self.raw["days"][0]["items"][0])
        other_ids = {i["event_id"] for i in self.raw["days"][1]["items"]}
        response = self.preview(day_index=0, confirmed=True)
        self.assertEqual(response.status_code, 200, response.data)
        items = response.data["trip"]["days"][0]["items"]
        self.assertIn(locked["key"], [i["key"] for i in items])
        self.assertFalse(other_ids & {i["event_id"] for i in items})

    def test_regenerate_requires_confirmation_and_no_match_preserves_selection(self):
        self.raw["days"][0]["items"] = [self.item()]
        self.assertTrue(self.preview().data["requires_confirmation"])
        self.raw["preferences"]["budget_max"] = 0
        response = self.preview(confirmed=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["trip"]["days"][0]["items"][0]["key"], "one")

    def test_regeneration_keeps_locked_activity_after_the_morning_slot(self):
        self.raw["days"][0]["items"] = [
            self.item(event=self.events[0], key="morning", slot_type="breakfast"),
            self.item(event=self.events[1], key="locked-visit", locked=True),
            self.item(event=self.events[2], key="midday", slot_type="lunch"),
        ]
        response = self.preview(day_index=0, confirmed=True)
        self.assertEqual(response.status_code, 200, response.data)
        items = response.data["trip"]["days"][0]["items"]
        self.assertEqual(items[1]["key"], "locked-visit")
        self.assertTrue(items[1]["locked"])
        self.assertNotEqual(items[0]["key"], "morning")
        self.assertEqual(len(items), 5)

    def test_regenerating_fully_locked_day_does_not_append_more_activities(self):
        self.raw["days"][0]["items"] = [
            self.item(event=event, key=f"locked-{index}", locked=True)
            for index, event in enumerate(self.events[:5])
        ]
        response = self.preview(day_index=0, confirmed=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["key"] for item in response.data["trip"]["days"][0]["items"]},
            {f"locked-{index}" for index in range(5)},
        )

    def test_manual_out_of_budget_requires_explicit_override(self):
        self.raw["preferences"]["budget_max"] = 0
        self.raw["days"][0]["items"] = [self.item(source="manual")]
        self.assertEqual(self.preview(action="validate").status_code, 400)
        self.raw["days"][0]["items"][0]["override_preferences"] = True
        response = self.preview(action="validate")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["trip"]["days"][0]["items"][0]["warnings"])

    def test_no_alternative_preserves_unlocked_items_even_when_another_item_is_locked(
        self,
    ):
        self.raw["preferences"]["budget_max"] = 0
        self.raw["days"][0]["items"] = [
            self.item(locked=True),
            self.item(event=self.events[1], key="unlocked"),
        ]
        response = self.preview(confirmed=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["key"] for item in response.data["trip"]["days"][0]["items"]},
            {"one", "unlocked"},
        )
        self.assertIn(0, response.data["preserved_days"])

    def test_reviewed_place_without_rating_is_eligible_until_user_requires_rating(self):
        event = self.events[0]
        event.rating = None
        event.last_verified_at = timezone.now()
        event.save()
        Event.objects.exclude(pk=event.pk).update(is_active=False)
        self.raw["preferences"]["min_rating"] = None
        response = self.preview()
        self.assertEqual(
            response.data["trip"]["days"][0]["items"][0]["event_id"], event.pk
        )
        self.raw["preferences"]["min_rating"] = 4
        response = self.preview()
        self.assertEqual(response.data["trip"]["days"][0]["items"], [])

    def test_decimal_rating_threshold_does_not_round_equal_ratings_out(self):
        from decimal import Decimal

        event = self.events[0]
        event.rating = Decimal("4.2")
        event.save()
        Event.objects.exclude(pk=event.pk).update(is_active=False)
        self.raw["preferences"]["min_rating"] = 4.2
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["trip"]["days"][0]["items"][0]["event_id"], event.pk
        )

    def test_duplicate_same_day_and_invalid_id_rejected(self):
        self.raw["days"][0]["items"] = [self.item(), self.item(key="two")]
        self.assertEqual(self.preview(action="validate").status_code, 400)
        self.raw["days"][0]["items"] = [{"event_id": True}]
        self.assertEqual(self.preview(action="validate").status_code, 400)

    def test_maximum_duration_and_dates_are_validated(self):
        self.raw["duration"] = 31
        self.assertEqual(self.preview().status_code, 400)
        self.raw["duration"] = 2
        self.raw["start_date"] = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.preview().status_code, 400)

    def test_availability_review_moves_multiple_unpublished_places_without_losing_locks(
        self,
    ):
        self.raw["days"][0]["items"] = [
            self.item(locked=True),
            self.item(event=self.events[1], key="second"),
        ]
        Event.objects.filter(pk__in=[self.events[0].pk, self.events[1].pk]).update(
            is_active=False
        )
        response = self.preview(
            action="dates", start_date=self.date.isoformat(), duration=2
        )
        self.assertTrue(response.data["requires_confirmation"])
        response = self.preview(
            action="dates", start_date=self.date.isoformat(), duration=2, confirmed=True
        )
        self.assertEqual(response.status_code, 200)
        trip = response.data["trip"]
        self.assertEqual(trip["days"][0]["items"], [])
        self.assertEqual(
            {item["key"] for item in trip["unscheduled"]}, {"one", "second"}
        )
        self.assertTrue(
            next(item for item in trip["unscheduled"] if item["key"] == "one")["locked"]
        )

    def test_legacy_migration_is_idempotent_and_preserves_originals(self):
        plan = DailyPlan.objects.create(user=self.user, date=self.date)
        plan.events.add(self.events[0], self.events[1])
        item = DailyPlanItem.objects.create(
            plan=plan, event=self.events[0], slot_type="activity", locked=True
        )
        favorite = Favorite.objects.create(user=self.user, event=self.events[0])
        migrate = import_module(
            "daily_plan.migrations.0006_preserve_legacy_trips"
        ).preserve_legacy_trips
        editor = connection.schema_editor()
        migrate(apps, editor)
        migrate(apps, editor)
        copied = Trip.objects.get(legacy_plan=plan)
        self.assertEqual(copied.activities.count(), 2)
        self.assertTrue(copied.activities.get(event=self.events[0]).locked)
        self.assertTrue(DailyPlanItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())
        self.assertEqual(plan.events.count(), 2)

    def test_guest_pages_are_public_in_both_languages(self):
        for path in ("/trips/", "/ar/trips/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'id="tripApp"')

    def test_classic_preferences_do_not_offer_unimplemented_age_or_traveler_controls(
        self,
    ):
        self.client.force_login(self.user)
        response = self.client.get("/onboarding/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="travelers"')
        self.assertNotContains(response, 'class="age-check')

    def test_guest_draft_expiry_and_read_does_not_extend_it(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is unavailable")
        script = r"""
const assert=require('node:assert/strict');
const drafts=require('./static/js/trip_drafts.js');
assert.equal(drafts.riyadhDate(new Date('2026-10-20T22:00:00Z')),'2026-10-21');
const memory=new Map();const storage={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
drafts.save(storage,{name:'Guest'},1000);
assert.equal(drafts.load(storage,1001).name,'Guest');
assert.equal(JSON.parse(storage.getItem(drafts.KEY)).editedAt,1000);
assert.equal(drafts.load(storage,1000+drafts.TTL),null);
drafts.save(storage,{name:'Edited'},5000);
assert.equal(drafts.load(storage,5000+drafts.TTL-1).name,'Edited');
assert.equal(drafts.load(storage,5000+drafts.TTL),null);
"""
        result = subprocess.run(
            [node, "-e", script],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
