from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from .models import Trip


class LegacyTripUpgradeTests(TransactionTestCase):
    def test_real_schema_upgrade_preserves_legacy_data_and_copies_locks(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        legacy_target = [("daily_plan", "0004_backfill_dailyplan_items")]
        executor.migrate(legacy_target)
        state_targets = [
            target for target in latest if target[0] != "daily_plan"
        ] + legacy_target
        historical = executor.loader.project_state(state_targets).apps
        User = historical.get_model("auth", "User")
        Event = historical.get_model("events", "Event")
        Favorite = historical.get_model("events", "Favorite")
        Plan = historical.get_model("daily_plan", "DailyPlan")
        Item = historical.get_model("daily_plan", "DailyPlanItem")
        user = User.objects.create(username="synthetic-upgrade-owner")
        events = [
            Event.objects.create(
                title=f"Synthetic upgrade {index}",
                category="heritage",
                date=timezone.now(),
            )
            for index in range(2)
        ]
        plan = Plan.objects.create(
            user_id=user.pk, date=timezone.localdate() + timedelta(days=5)
        )
        plan.events.set(events)
        item = Item.objects.create(
            plan=plan,
            event=events[0],
            slot_type="evening",
            order=4,
            source="manual",
            locked=True,
        )
        Favorite.objects.create(user=user, event=events[0])
        MigrationExecutor(connection).migrate(latest)
        trip = Trip.objects.get(legacy_plan_id=plan.pk)
        self.assertEqual(trip.user_id, user.pk)
        self.assertEqual(trip.activities.count(), 2)
        copied = trip.activities.get(event_id=events[0].pk)
        self.assertTrue(copied.locked)
        self.assertEqual(copied.slot_type, "evening")
        self.assertEqual(copied.position, 4)
        self.assertTrue(Plan.objects.filter(pk=plan.pk).exists())
        self.assertTrue(Item.objects.filter(pk=item.pk, locked=True).exists())
        self.assertEqual(Favorite.objects.filter(user=user).count(), 1)
        self.assertEqual(plan.events.count(), 2)
        connection.check_constraints()
