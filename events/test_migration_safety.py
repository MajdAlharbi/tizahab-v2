from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.utils import timezone


class PlaceMigrationSafetyTests(TransactionTestCase):
    original_names = (
        "0016_curate_verified_places",
        "0017_expand_verified_riyadh_places",
    )
    replacement_names = ("0016_safe_curated_places", "0017_safe_expand_places")

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        self.target = [("events", "0017_safe_expand_places")]
        # Build a real historical schema before simulating the old deployment
        # records. An already-applied newer leaf would otherwise skip its parents.
        executor.migrate(self.target)
        self.historical_apps = executor.loader.project_state(
            self.target + [("daily_plan", "0004_backfill_dailyplan_items")]
        ).apps
        self.addCleanup(self.restore_latest)
        self.recorder = MigrationRecorder(connection)
        self.names = self.original_names + self.replacement_names
        self.recorded = set(
            self.recorder.migration_qs.filter(
                app="events", name__in=self.names
            ).values_list("name", flat=True)
        )
        self.addCleanup(self.restore_history)

    def restore_latest(self):
        MigrationExecutor(connection).migrate(self.latest_targets)

    def restore_history(self):
        self.recorder.migration_qs.filter(app="events", name__in=self.names).delete()
        for name in self.recorded:
            self.recorder.record_applied("events", name)

    def verify_upgrade(self, applied):
        Event = self.historical_apps.get_model("events", "Event")
        Favorite = self.historical_apps.get_model("events", "Favorite")
        DailyPlan = self.historical_apps.get_model("daily_plan", "DailyPlan")
        DailyPlanItem = self.historical_apps.get_model("daily_plan", "DailyPlanItem")
        self.recorder.migration_qs.filter(app="events", name__in=self.names).delete()
        for name in self.original_names[:applied]:
            self.recorder.record_applied("events", name)
        user = get_user_model().objects.create_user(username="migration-owner")
        legacy = import_module("events.migrations.0016_curate_verified_places")
        title = legacy.fixture_records()[0]["fields"]["title"]
        kept = [
            Event.objects.create(
                title=title if index else "Personal event",
                category="culture",
                date=timezone.now(),
                description="Keep my description",
                location="Personal location",
            )
            for index in range(3)
        ]
        plan = DailyPlan.objects.create(user_id=user.pk, date=timezone.localdate())
        plan.events.set(kept)
        for index, event in enumerate(kept):
            Favorite.objects.create(user_id=user.pk, event=event)
            DailyPlanItem.objects.create(
                plan=plan, event=event, slot_type="activity", order=index
            )
        count_before = Event.objects.count()
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(self.target)
        self.assertFalse(
            any(migration.name in self.original_names for migration, _ in pending)
        )
        executor.migrate(self.target)
        for event in kept:
            event.refresh_from_db()
            self.assertEqual(event.description, "Keep my description")
            self.assertEqual(event.location, "Personal location")
        self.assertEqual(Favorite.objects.filter(user_id=user.pk).count(), 3)
        self.assertEqual(plan.items.count(), 3)
        self.assertEqual(plan.events.count(), 3)
        if applied < 2:
            self.assertGreater(Event.objects.count(), 3)
        else:
            self.assertEqual(Event.objects.count(), count_before)

    def test_upgrade_before_both_legacy_migrations_preserves_data(self):
        self.verify_upgrade(0)

    def test_upgrade_after_only_0016_preserves_data(self):
        self.verify_upgrade(1)

    def test_upgrade_after_both_does_not_replay_or_overwrite(self):
        self.verify_upgrade(2)

    def test_legacy_operation_would_cascade_to_favorites_and_plan_items(self):
        Event = self.historical_apps.get_model("events", "Event")
        Favorite = self.historical_apps.get_model("events", "Favorite")
        DailyPlan = self.historical_apps.get_model("daily_plan", "DailyPlan")
        DailyPlanItem = self.historical_apps.get_model("daily_plan", "DailyPlanItem")
        user = get_user_model().objects.create_user(username="legacy-owner")
        event = Event.objects.create(
            title="Custom", category="culture", date=timezone.now()
        )
        plan = DailyPlan.objects.create(user_id=user.pk, date=timezone.localdate())
        plan.events.add(event)
        Favorite.objects.create(user_id=user.pk, event=event)
        DailyPlanItem.objects.create(plan=plan, event=event, slot_type="activity")
        legacy = import_module("events.migrations.0016_curate_verified_places")
        historical_apps = (
            MigrationExecutor(connection)
            .loader.project_state(
                self.target + [("daily_plan", "0004_backfill_dailyplan_items")]
            )
            .apps
        )

        with patch.object(legacy, "fixture_records", return_value=[]):
            # This demonstration runs exclusively in Django's disposable test DB.
            legacy.clean_and_sync_places(historical_apps, None)
        self.assertTrue(DailyPlan.objects.filter(pk=plan.pk).exists())
        self.assertEqual(plan.items.count(), 0)
        self.assertEqual(plan.events.count(), 0)
        self.assertFalse(Favorite.objects.filter(user_id=user.pk).exists())
