from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient
import requests

from .catalog import clean_record, review_record, sync_source
from .models import CatalogSource, ContentAuditLog, Event, SourceRecord
from .providers import (
    ADAPTERS,
    ProviderBlocked,
    ProviderError,
    fetch_osm,
    fetch_ticketmaster,
)


@override_settings(
    CATALOG_SYNC_ENABLED=True, CATALOG_USER_AGENT="Tizahab synthetic test"
)
class CatalogSafetyTests(TestCase):
    def setUp(self):
        self.source, _ = CatalogSource.objects.get_or_create(provider="osm")
        self.source.enabled = True
        self.source.next_sync_at = None
        self.source.save()
        self.manager = User.objects.create_user("catalog-editor", is_staff=True)
        self.manager.user_permissions.add(
            Permission.objects.get(codename="change_event")
        )
        self.record = {
            "external_id": "node/123",
            "title": "Synthetic verified heritage",
            "category": "heritage",
            "description": "",
            "location": "Riyadh",
            "latitude": 24.7,
            "longitude": 46.7,
            "source": "OpenStreetMap contributors",
            "source_url": "https://www.openstreetmap.org/node/123",
            "source_license": "ODbL 1.0",
            "price": None,
            "rating": None,
        }

    def run_sync(self, records):
        with patch.dict(ADAPTERS, {"osm": lambda: records}):
            return sync_source(self.source.pk)

    def due(self):
        CatalogSource.objects.filter(pk=self.source.pk).update(next_sync_at=None)

    def test_new_valid_record_is_queued_not_published(self):
        count = Event.objects.count()
        run = self.run_sync([self.record])
        self.assertEqual(run.status, "success")
        self.assertEqual(run.queued, 1)
        self.assertEqual(Event.objects.count(), count)
        self.assertEqual(SourceRecord.objects.get(source=self.source).status, "pending")

    def test_empty_response_never_removes_existing_places(self):
        self.run_sync([self.record])
        count = Event.objects.count()
        self.due()
        run = self.run_sync([])
        self.assertEqual(run.status, "empty")
        self.assertEqual(Event.objects.count(), count)
        self.assertEqual(SourceRecord.objects.filter(source=self.source).count(), 1)

    def test_invalid_batch_rolls_back_queue_and_preserves_catalog(self):
        count = Event.objects.count()
        invalid = {**self.record, "external_id": "node/999", "latitude": 999}
        run = self.run_sync([self.record, invalid])
        self.assertEqual(run.status, "failed")
        self.assertEqual(Event.objects.count(), count)
        self.assertFalse(SourceRecord.objects.filter(source=self.source).exists())

    def test_review_publishes_and_logs_human_decision(self):
        self.run_sync([self.record])
        record = SourceRecord.objects.get(source=self.source)
        reviewed = review_record(record.pk, self.manager, True)
        self.assertEqual(reviewed.status, "approved")
        self.assertTrue(reviewed.event.is_active)
        self.assertEqual(reviewed.event.source_license, "ODbL 1.0")
        self.assertIsNotNone(reviewed.event.last_verified_at)
        self.assertTrue(
            ContentAuditLog.objects.filter(
                action="source.approve", actor=self.manager
            ).exists()
        )

    def test_significant_update_does_not_overwrite_published_record(self):
        self.run_sync([self.record])
        record = SourceRecord.objects.get(source=self.source)
        published = review_record(record.pk, self.manager, True).event
        self.due()
        self.run_sync(
            [{**self.record, "title": "Synthetic changed title", "price": "75.00"}]
        )
        published.refresh_from_db()
        self.assertEqual(published.title, self.record["title"])
        self.assertIsNone(published.price)
        record.refresh_from_db()
        self.assertEqual(record.status, "pending")

    def test_repeat_payload_deduplicates_without_reopening_rejected_record(self):
        self.run_sync([self.record, self.record])
        record = SourceRecord.objects.get(source=self.source)
        review_record(record.pk, self.manager, False)
        self.due()
        run = self.run_sync([self.record])
        record.refresh_from_db()
        self.assertEqual(SourceRecord.objects.filter(source=self.source).count(), 1)
        self.assertEqual(run.queued, 0)
        self.assertEqual(record.status, "rejected")

    def test_unknown_provider_fields_do_not_erase_known_curated_values(self):
        event = Event.objects.create(
            title=self.record["title"],
            category="heritage",
            description="Curator's verified description",
            date=timezone.now(),
            latitude=24.7,
            longitude=46.7,
            price=35,
            rating=4.5,
        )
        self.run_sync([self.record])
        record = SourceRecord.objects.get(source=self.source)
        self.assertEqual(record.event_id, event.pk)
        review_record(record.pk, self.manager, True)
        event.refresh_from_db()
        self.assertEqual(event.description, "Curator's verified description")
        self.assertEqual(event.price, 35)
        self.assertEqual(event.rating, 4.5)

    def test_provider_failure_preserves_catalog_and_does_not_expose_exception_secrets(
        self,
    ):
        count = Event.objects.count()
        with patch.dict(
            ADAPTERS,
            {"osm": Mock(side_effect=ProviderError("synthetic-secret-not-for-logs"))},
        ):
            run = sync_source(self.source.pk)
        self.assertEqual(run.status, "failed")
        self.assertNotIn("synthetic-secret", run.error)
        self.assertEqual(Event.objects.count(), count)

    def test_schedule_and_lease_prevent_duplicate_network_jobs(self):
        self.run_sync([])
        with self.assertRaises(ProviderBlocked):
            self.run_sync([])
        self.due()
        CatalogSource.objects.filter(pk=self.source.pk).update(
            lease_until=timezone.now() + timedelta(minutes=1)
        )
        with self.assertRaises(ProviderBlocked):
            self.run_sync([])

    @override_settings(CATALOG_SYNC_ENABLED=False)
    def test_live_sync_is_disabled_by_default(self):
        with patch.dict(
            ADAPTERS, {"osm": Mock(side_effect=AssertionError("No network expected"))}
        ):
            run = sync_source(self.source.pk)
        self.assertEqual(run.status, "blocked")
        self.source.refresh_from_db()
        self.assertIsNone(self.source.next_sync_at)

    def test_missing_event_date_rejected_without_inventing_schedule(self):
        with self.assertRaises(serializers.ValidationError):
            clean_record({**self.record, "category": "events"})

    def test_openstreetmap_adapter_preserves_unknown_price_hours_and_rating(self):
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {
            "elements": [
                {
                    "type": "node",
                    "id": 123,
                    "lat": 24.7,
                    "lon": 46.7,
                    "tags": {"name": "Synthetic Museum", "tourism": "museum"},
                }
            ]
        }
        with patch("events.providers.requests.post", return_value=response) as post:
            result = fetch_osm()
        self.assertIsNone(result[0]["price"])
        self.assertIsNone(result[0]["rating"])
        self.assertEqual(result[0]["opening_hours_text"], "")
        self.assertNotIn("date", result[0])
        self.assertTrue(post.call_args.kwargs["timeout"])

    def test_openstreetmap_timeout_and_malformed_response_are_handled(self):
        with patch("events.providers.requests.post", side_effect=requests.Timeout):
            with self.assertRaises(ProviderError):
                fetch_osm()
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {"remark": "timeout"}
        with patch("events.providers.requests.post", return_value=response):
            with self.assertRaises(ProviderError):
                fetch_osm()

    def test_ticketmaster_is_honestly_blocked(self):
        with self.assertRaises(ProviderBlocked):
            fetch_ticketmaster()

    def test_expired_event_not_in_upcoming_discover(self):
        expired = Event.objects.create(
            title="Synthetic expired",
            category="events",
            date=timezone.now() - timedelta(days=5),
        )
        client = APIClient()
        response = client.get("/api/events/?search=Synthetic+expired")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            expired.pk, [event["id"] for event in response.data["results"]]
        )

    def test_invalid_admin_coordinates_and_rating_rejected(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        for field, value in (
            ("rating", 8),
            ("rating", -1),
            ("latitude", 999),
            ("longitude", -999),
            ("latitude", "NaN"),
            ("longitude", "Infinity"),
        ):
            response = client.post(
                "/api/events/admin/events/",
                {
                    "title": "Synthetic invalid",
                    "date": timezone.now().isoformat(),
                    "category": "culture",
                    "location": "Riyadh",
                    field: value,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400, response.data)
