from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from django.utils import timezone
from rest_framework.test import APIClient


class BrandInterfaceTests(TestCase):
    def setUp(self):
        # Page rendering must not inherit password-reset throttles from another test.
        cache.clear()

    def test_auth_language_round_trip_stays_on_the_ui_and_preserves_query(self):
        for page in ("login", "signup"):
            with self.subTest(page=page):
                english = f"/{page}/?next=%2Fdaily-plan%2F"
                arabic = f"/ar/{page}/?next=%2Fdaily-plan%2F"
                response = self.client.post(
                    "/i18n/setlang/", {"language": "ar", "next": english}
                )
                self.assertRedirects(response, arabic)
                page_response = self.client.get(arabic)
                self.assertContains(page_response, f'name="next" value="{english}"')
                response = self.client.post(
                    "/i18n/setlang/", {"language": "en", "next": english}
                )
                self.assertRedirects(response, english)

        response = self.client.get("/ar/profile/")
        self.assertRedirects(response, "/ar/login/?next=/ar/profile/")
        response = self.client.get("/profile/")
        self.assertRedirects(response, "/login/?next=/profile/")

    def test_api_and_page_names_resolve_to_their_existing_distinct_urls(self):
        with override("en"):
            self.assertEqual(reverse("login"), "/login/")
            self.assertEqual(reverse("signup"), "/signup/")
            self.assertEqual(reverse("api-login"), "/api/auth/login/")
            self.assertEqual(reverse("api-signup"), "/api/auth/signup/")

    @override_settings(
        SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="",
        SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET="",
        SOCIAL_AUTH_FACEBOOK_KEY="",
        SOCIAL_AUTH_FACEBOOK_SECRET="",
    )
    def test_unconfigured_social_providers_do_not_advertise_broken_login(self):
        for url in ("/login/", "/signup/"):
            response = self.client.get(url)
            self.assertNotContains(response, "/auth/login/google-oauth2/")
            self.assertNotContains(response, "/auth/login/facebook/")

    @override_settings(
        SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="test-ui-client",
        SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET="test-ui-secret-not-for-rendering",
        SOCIAL_AUTH_FACEBOOK_KEY="",
        SOCIAL_AUTH_FACEBOOK_SECRET="",
    )
    def test_configured_social_login_is_preserved_without_exposing_credentials(self):
        response = self.client.get("/login/")
        self.assertContains(response, "/auth/login/google-oauth2/")
        self.assertNotContains(response, "test-ui-client")
        self.assertNotContains(response, "test-ui-secret-not-for-rendering")

    def test_active_pages_render_both_directions_and_use_the_approved_logo(self):
        self.client.force_login(
            get_user_model().objects.create_user(username="brand-ui")
        )
        pages = (
            "",
            "home/",
            "events/page/",
            "daily-plan/",
            "onboarding/",
            "profile/",
            "settings/",
            "travel-guide/",
            "booking/",
            "car-rental/",
            "login/",
            "signup/",
            "forgot-password/",
        )
        for prefix, language, direction in (("/", "en", "ltr"), ("/ar/", "ar", "rtl")):
            for page in pages:
                with self.subTest(language=language, page=page):
                    response = self.client.get(prefix + page)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(
                        response, f'lang="{language}" id="htmlRoot" dir="{direction}"'
                    )
                    self.assertContains(response, "/static/brand/logo.svg")
                    self.assertContains(response, 'alt="Tizahab"')

        self.client.force_login(
            get_user_model().objects.create_user(
                username="brand-staff", is_staff=True, is_superuser=True
            )
        )
        for url in ("/admin-panel/", "/ar/admin-panel/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "/static/brand/logo.svg")
            self.assertContains(response, "<h1>")

    def test_admin_pagination_matches_the_table_page_size_without_skipping_places(self):
        from events.models import Event

        staff = get_user_model().objects.create_user(
            username="ui-pagination", is_staff=True, is_superuser=True
        )
        api_client = APIClient()
        api_client.force_authenticate(user=staff)
        Event.objects.bulk_create(
            [
                Event(
                    title=f"UI pagination verification {index}",
                    date=timezone.now(),
                    description="Synthetic pagination fixture",
                    category="culture",
                    location="Riyadh",
                )
                for index in range(27)
            ]
        )
        endpoint = (
            "/api/events/admin/events/?search=UI+pagination+verification&page_size=20"
        )
        first = api_client.get(endpoint)
        second = api_client.get(endpoint + "&page=2")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["count"], 27)
        self.assertEqual(len(first.data["results"]), 20)
        self.assertEqual(len(second.data["results"]), 7)
        first_ids = {item["id"] for item in first.data["results"]}
        second_ids = {item["id"] for item in second.data["results"]}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(len(first_ids | second_ids), 27)
        api_client.force_authenticate(
            user=get_user_model().objects.create_user(username="ui-reader")
        )
        self.assertEqual(api_client.get(endpoint).status_code, 403)

    def test_rate_limit_and_expired_reset_link_keep_brand_and_recovery_actions(self):
        for prefix in ("/", "/ar/"):
            with self.subTest(prefix=prefix):
                with patch(
                    "django_ratelimit.decorators.is_ratelimited", return_value=True
                ):
                    response = self.client.get(prefix + "forgot-password/")
                self.assertEqual(response.status_code, 403)
                self.assertContains(response, "/static/brand/logo.svg", status_code=403)
                self.assertContains(response, 'role="alert"', status_code=403)
                response = self.client.get(
                    prefix + "reset-password/expired-ui-fixture/"
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, prefix + "forgot-password/")
                self.assertNotContains(response, 'name="password1"')
