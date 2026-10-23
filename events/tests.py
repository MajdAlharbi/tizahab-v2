from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import json
from pathlib import Path
from rest_framework.test import APIClient
from rest_framework import status

from events.models import Event, Favorite
from events.views import _parse_date, _apply_date_range_filter
from accounts.models import UserPreferences


def make_user(email="ev@test.com", password="StrongPass1!"):
    return User.objects.create_user(username=email, email=email, password=password)


def make_event(title="Test Event", category="food", price=50.00, **kwargs):
    defaults = {
        "description": "A test event",
        "date": timezone.now(),
        "location": "Riyadh",
        "price": price,
        "price_range": "",
    }
    defaults.update(kwargs)
    return Event.objects.create(title=title, category=category, **defaults)


def auth_client(user, password="StrongPass1!"):
    client = APIClient()
    response = client.post(
        "/api/auth/login/", {"email": user.email, "password": password}
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


class ParseDateTests(TestCase):
    def test_valid_date(self):
        result = _parse_date("2026-06-15")
        self.assertEqual(str(result), "2026-06-15")

    def test_invalid_date_returns_none(self):
        self.assertIsNone(_parse_date("not-a-date"))
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date(None))


class EventListAPITests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = auth_client(self.user)
        make_event("Food Place", category="food", price=50)
        make_event("Culture Spot", category="culture", price=0)
        make_event("Nature Park", category="nature", price=0)

    def test_list_returns_all_events(self):
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Pagination: check 'results' key exists
        data = response.data
        results = data.get("results", data)
        self.assertGreaterEqual(len(results), 3)

    def test_filter_by_category(self):
        response = self.client.get("/api/events/?category=food")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for event in results:
            self.assertEqual(event["category"], "food")

    def test_public_category_filters_return_only_requested_category(self):
        client = APIClient()
        for category in ("food", "culture", "nature"):
            response = client.get(f"/api/events/?category={category}")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            results = response.data.get("results", response.data)
            self.assertGreater(len(results), 0)
            self.assertTrue(
                all(event["category"] == category for event in results),
                msg=f"Unexpected category in {category} response: {results}",
            )

    def test_legacy_category_alias_is_accepted(self):
        response = self.client.get("/api/events/?category=restaurant")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertTrue(all(event["category"] == "food" for event in results))

    def test_search_by_title(self):
        response = self.client.get("/api/events/?search=Culture")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        titles = [e["title"] for e in results]
        self.assertTrue(any("Culture" in t for t in titles))

    def test_invalid_date_returns_400(self):
        response = self.client.get("/api/events/filtered/?date_from=baddate")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_category_returns_400(self):
        response = self.client.get("/api/events/?category=music")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_event_list_date_returns_400(self):
        response = self.client.get("/api/events/?date=baddate")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_events_public_no_auth_required(self):
        # EventListAPIView uses AllowAny — unauthenticated requests should succeed
        client = APIClient()
        response = client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_serializer_includes_price_and_dates(self):
        response = self.client.get("/api/events/")
        results = response.data.get("results", response.data)
        self.assertTrue(len(results) > 0)
        first = results[0]
        self.assertIn("price", first)
        self.assertIn("start_date", first)
        self.assertIn("end_date", first)
        self.assertIn("area", first)
        self.assertIn("image_url", first)

    def test_serializer_returns_event_image_url(self):
        image_url = "https://example.com/place.jpg"
        make_event("Photo Place", category="nature", image_url=image_url)

        response = self.client.get("/api/events/?search=Photo%20Place")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(results[0]["image_url"], image_url)

    def test_filter_by_area(self):
        make_event("North Place", category="nature", area="North Riyadh")
        make_event("South Place", category="nature", area="South Riyadh")

        response = self.client.get("/api/events/", {"area": "North Riyadh"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertGreater(len(results), 0)
        self.assertTrue(all(event["area"] == "North Riyadh" for event in results))

    def test_invalid_area_returns_400(self):
        response = self.client.get("/api/events/?area=Unknown")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FilteredEventsAPITests(TestCase):
    def setUp(self):
        self.user = make_user("filt@test.com")
        pref, _ = UserPreferences.objects.get_or_create(user=self.user)
        pref.interests = ["food", "culture"]
        pref.budget_max = 100
        pref.save()
        self.client = auth_client(self.user)

        make_event("Cheap Food", category="food", price=30)
        make_event("Expensive Food", category="food", price=200)
        make_event("Free Culture", category="culture", price=0)
        make_event("Nature Park", category="nature", price=0)

    def test_filters_by_user_interests(self):
        response = self.client.get("/api/events/filtered/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        categories = {e["category"] for e in results}
        self.assertNotIn("nature", categories)

    def test_budget_filter_excludes_expensive(self):
        response = self.client.get("/api/events/filtered/")
        results = response.data.get("results", response.data)
        for event in results:
            price = event.get("price")
            if price is not None:
                self.assertLessEqual(float(price), 100)

    def test_null_price_events_included_with_budget(self):
        make_event("No Price Food", category="food", price=None)
        response = self.client.get("/api/events/filtered/")
        results = response.data.get("results", response.data)
        titles = [e["title"] for e in results]
        self.assertIn("No Price Food", titles)

    def test_invalid_date_range_returns_400(self):
        response = self.client.get(
            "/api/events/filtered/?date_from=2026-06-16&date_to=2026-06-15"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EventAvailabilityAPITests(TestCase):
    def setUp(self):
        self.user = make_user("availability@test.com")
        pref, _ = UserPreferences.objects.get_or_create(user=self.user)
        pref.interests = ["events", "food"]
        pref.save()
        self.client = auth_client(self.user)

        today = timezone.now()
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)
        self.live_event = make_event(
            "Live Festival",
            category="events",
            start_date=today,
            end_date=tomorrow,
        )
        self.future_event = make_event(
            "Future Expo",
            category="events",
            start_date=next_week,
            end_date=next_week,
        )
        self.food_place = make_event("Anyday Food", category="food")

    def test_event_list_date_filter_respects_event_window(self):
        target_date = timezone.localdate().isoformat()
        response = self.client.get(f"/api/events/?date={target_date}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        titles = [event["title"] for event in results]
        self.assertIn("Live Festival", titles)
        self.assertNotIn("Future Expo", titles)

    def test_filtered_events_date_range_excludes_inactive_future_only_events(self):
        target_date = timezone.localdate().isoformat()
        response = self.client.get(
            f"/api/events/filtered/?date_from={target_date}&date_to={target_date}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        titles = [event["title"] for event in results]
        self.assertIn("Live Festival", titles)
        self.assertIn("Anyday Food", titles)
        self.assertNotIn("Future Expo", titles)


class EventModelTests(TestCase):
    def test_event_str(self):
        event = make_event("My Event")
        self.assertEqual(str(event), "My Event")

    def test_event_price_nullable(self):
        event = make_event("Free Event", price=None)
        self.assertIsNone(event.price)

    def test_event_start_end_date_nullable(self):
        event = make_event("Always Open")
        self.assertIsNone(event.start_date)
        self.assertIsNone(event.end_date)

    def test_legacy_category_is_normalized_on_save(self):
        event = make_event("Legacy Restaurant", category="restaurant")
        self.assertEqual(event.category, "food")


class RiyadhFixtureDataTests(TestCase):
    def test_fixture_does_not_use_placeholder_image_service(self):
        fixture_path = (
            Path(__file__).resolve().parent / "fixtures" / "riyadh_places.json"
        )
        records = json.loads(fixture_path.read_text(encoding="utf-8-sig"))

        bad_images = [
            record["fields"]["title"]
            for record in records
            if record["fields"]
            .get("image_url", "")
            .startswith("https://loremflickr.com/")
        ]

        self.assertEqual(bad_images, [])


class FavoritesAPITests(TestCase):
    def setUp(self):
        self.user = make_user("fav@test.com")
        self.other_user = make_user("other-fav@test.com")
        self.client = auth_client(self.user)
        self.event1 = make_event("Fav Event 1", category="food")
        self.event2 = make_event("Fav Event 2", category="culture")

    def test_list_favorites_returns_only_own_items(self):
        Favorite.objects.create(user=self.user, event=self.event1)
        Favorite.objects.create(user=self.other_user, event=self.event2)

        response = self.client.get("/api/events/favorites/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["event"]["id"], self.event1.id)

    def test_add_favorite_creates_record(self):
        response = self.client.post(
            "/api/events/favorites/",
            {"event_id": self.event1.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Favorite.objects.filter(user=self.user, event=self.event1).exists()
        )

    def test_add_duplicate_favorite_returns_400(self):
        Favorite.objects.create(user=self.user, event=self.event1)
        response = self.client.post(
            "/api/events/favorites/",
            {"event_id": self.event1.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_add_favorites_returns_migrated_and_skipped(self):
        Favorite.objects.create(user=self.user, event=self.event1)
        response = self.client.post(
            "/api/events/favorites/bulk/",
            {"event_ids": [self.event1.id, self.event2.id, "bad", 999999]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["migrated"], 1)
        self.assertEqual(response.data["skipped"], 3)

    def test_delete_favorite(self):
        Favorite.objects.create(user=self.user, event=self.event1)
        response = self.client.delete(f"/api/events/favorites/{self.event1.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Favorite.objects.filter(user=self.user, event=self.event1).exists()
        )

    def test_delete_missing_favorite_returns_404(self):
        response = self.client.delete(f"/api/events/favorites/{self.event1.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_favorites_require_auth(self):
        client = APIClient()
        response = client.get("/api/events/favorites/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
