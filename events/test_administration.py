from datetime import timedelta

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from daily_plan.models import Trip
from daily_plan.trip_services import save_document
from .models import CatalogSource, ContentAuditLog, Event, Favorite, SourceRecord


class AdministrationProductTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user("content-manager", is_staff=True)
        cls.manager.groups.add(Group.objects.get(name="Content Manager"))
        cls.superuser = User.objects.create_superuser(
            "super-admin", "super@example.test", "Synthetic123!"
        )
        cls.member = User.objects.create_user("trip-member")
        cls.event = Event.objects.create(
            title="Synthetic admin destination",
            description="",
            category="heritage",
            date=timezone.now(),
            location="Riyadh",
            latitude=24.7,
            longitude=46.7,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_content_manager_has_content_permissions_without_account_access(self):
        self.assertTrue(self.manager.has_perm("events.add_event"))
        self.assertFalse(self.manager.has_perm("auth.change_user"))
        self.assertEqual(self.client.get("/api/events/admin/events/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/admin/users/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                f"/api/auth/admin/users/{self.superuser.pk}/",
                {"is_active": False},
                format="json",
            ).status_code,
            403,
        )

    def test_model_admin_enforces_roles_even_if_user_permissions_were_granted(self):
        self.manager.user_permissions.add(
            Permission.objects.get(codename="change_user")
        )
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/admin/events/event/add/").status_code, 200)
        self.assertEqual(self.client.get("/admin/auth/user/").status_code, 403)
        self.assertEqual(
            self.client.get("/admin/accounts/userpreferences/").status_code, 403
        )

    def test_deactivation_keeps_favorites_and_private_trip_activities(self):
        favorite = Favorite.objects.create(user=self.member, event=self.event)
        raw = {
            "name": "Private",
            "start_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
            "duration": 1,
            "days": [
                {"items": [{"key": "keep", "event_id": self.event.pk, "locked": True}]}
            ],
        }
        trip = save_document(self.member, raw)
        response = self.client.delete(f"/api/events/admin/events/{self.event.pk}/")
        self.assertEqual(response.status_code, 204)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_active)
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())
        self.assertTrue(trip.activities.get().locked)
        self.assertEqual(
            APIClient().get(f"/api/events/{self.event.pk}/").status_code, 404
        )
        self.assertTrue(
            ContentAuditLog.objects.filter(action="event.deactivate").exists()
        )

    def test_event_end_cannot_precede_the_legacy_date_when_start_is_missing(self):
        response = self.client.post(
            "/api/events/admin/events/",
            {
                "title": "Synthetic invalid event window",
                "category": "events",
                "date": (timezone.now() + timedelta(days=20)).isoformat(),
                "end_date": (timezone.now() + timedelta(days=19)).isoformat(),
                "location": "Synthetic Riyadh location",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("end_date", response.data)
        self.assertFalse(
            Event.objects.filter(title="Synthetic invalid event window").exists()
        )

    def test_django_admin_model_validation_rejects_an_inverted_event_window(self):
        event = Event(
            title="Synthetic inverted event",
            category="events",
            date=timezone.now(),
            end_date=timezone.now() - timedelta(days=1),
            location="Riyadh",
        )
        with self.assertRaises(ValidationError) as error:
            event.full_clean()
        self.assertIn("end_date", error.exception.message_dict)

    def test_content_edit_has_audit_snapshot_and_review_timestamp(self):
        response = self.client.patch(
            f"/api/events/admin/events/{self.event.pk}/",
            {"title": "Synthetic edited title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        log = ContentAuditLog.objects.get(action="event.update")
        self.assertEqual(log.actor_id, self.manager.pk)
        self.assertEqual(log.before["title"], "Synthetic admin destination")
        self.assertEqual(log.after["title"], "Synthetic edited title")
        self.assertIsNotNone(response.data["last_verified_at"])

    def test_draft_content_is_not_public_even_if_active_requested(self):
        response = self.client.patch(
            f"/api/events/admin/events/{self.event.pk}/",
            {"publication_status": "draft", "is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(
            APIClient().get(f"/api/events/{self.event.pk}/").status_code, 404
        )

    def test_review_api_requires_current_snapshot_and_content_permission(self):
        source = CatalogSource.objects.get(provider="osm")
        record = SourceRecord.objects.create(
            source=source,
            external_id="node/77",
            payload={
                "title": "Synthetic provider place",
                "description": "",
                "category": "nature",
                "location": "Riyadh",
            },
        )
        url = f"/api/events/admin/review/{record.pk}/"
        self.assertEqual(
            self.client.post(url, {"decision": "approve"}, format="json").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url, {"decision": "approve", "last_seen_at": "stale"}, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url,
                {
                    "decision": "approve",
                    "last_seen_at": record.last_seen_at.isoformat(),
                },
                format="json",
            ).status_code,
            200,
        )
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/events/admin/review/").status_code, 403)
        self.assertEqual(self.client.get("/api/events/admin/audit/").status_code, 403)

    @override_settings(CATALOG_SYNC_ENABLED=False)
    def test_disabled_sync_is_reported_without_breaking_discovery(self):
        source = CatalogSource.objects.get(provider="osm")
        response = self.client.post(
            f"/api/events/admin/sources/{source.pk}/sync/", {}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(source.runs.get().status, "blocked")
        self.assertEqual(APIClient().get("/api/events/").status_code, 200)

    def test_content_dashboard_does_not_disclose_user_activity(self):
        response = self.client.get("/api/events/admin/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["total_users"])
        self.assertEqual(response.data["recent_activity"], [])
        self.assertIn("pending_reviews", response.data)
        self.client.force_login(self.manager)
        page = self.client.get("/admin-panel/")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="users-section"')
        self.assertContains(page, 'id="catalog-review"')

    def test_super_admin_deactivation_preserves_user_trips_and_blocks_self_deactivation(
        self,
    ):
        trip = Trip.objects.create(
            user=self.member,
            name="Keep private",
            start_date=timezone.localdate(),
            duration=1,
        )
        self.client.force_authenticate(self.superuser)
        self.assertEqual(
            self.client.delete(f"/api/auth/admin/users/{self.member.pk}/").status_code,
            204,
        )
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertTrue(Trip.objects.filter(pk=trip.pk).exists())
        response = self.client.patch(
            f"/api/auth/admin/users/{self.superuser.pk}/",
            {"is_active": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
