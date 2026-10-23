from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import Client


class InterfaceIntegrationTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_user(username="interface")
        )

    def test_arabic_dashboard_preserves_language_navigation_and_rtl_layout(self):
        response = self.client.get("/ar/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="ar" id="htmlRoot" dir="rtl"')
        self.assertContains(response, 'href="/ar/daily-plan/"')
        self.assertContains(response, 'href="/ar/trips/"')
        self.assertContains(response, 'class="site-header"')
        self.assertContains(response, 'aria-controls="sidebar" aria-expanded="false"')
        self.assertContains(response, 'class="site-drawer start-0"')
        self.assertContains(response, "start-0")
        self.assertContains(response, 'var l = "ar";')

    def test_header_search_submits_to_explore_and_notifications_are_disabled(self):
        response = self.client.get("/profile/")
        self.assertContains(
            response, 'action="/events/page/" method="get" role="search"'
        )
        self.assertContains(response, 'name="search" type="search"')
        self.assertContains(
            response,
            'disabled aria-disabled="true" aria-label="Notifications unavailable"',
        )

    def test_unimplemented_settings_are_marked_unavailable(self):
        response = self.client.get("/settings/")
        self.assertContains(
            response, 'aria-checked="false" aria-disabled="true"', count=7
        )
        self.assertNotContains(response, 'href="#"')
        self.assertContains(
            response, 'id="settingsLanguageForm" action="/i18n/setlang/" method="post"'
        )

    def test_language_form_applies_actual_server_language(self):
        response = self.client.post(
            "/i18n/setlang/", {"language": "ar", "next": "/settings/"}
        )
        self.assertRedirects(response, "/ar/settings/")
        self.assertEqual(response.cookies["django_language"].value, "ar")

    def test_csrf_protected_logout_prevents_session_token_rehydration(self):
        client = Client(enforce_csrf_checks=True)
        user = get_user_model().objects.create_user(username="logout-browser")
        client.force_login(user)
        self.assertEqual(client.get("/api/auth/session-token/").status_code, 200)
        self.assertEqual(client.get("/profile/").status_code, 200)
        response = client.post(
            "/logout/", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(client.get("/api/auth/session-token/").status_code, 403)

    def test_language_round_trip_preserves_plan_date_and_returns_to_english(self):
        english = "/daily-plan/?date=2099-11-03"
        arabic = "/ar/daily-plan/?date=2099-11-03"
        response = self.client.post(
            "/i18n/setlang/", {"language": "ar", "next": english}
        )
        self.assertRedirects(response, arabic)
        page = self.client.get(arabic)
        self.assertContains(page, f'name="next" value="{english}"')
        response = self.client.post(
            "/i18n/setlang/", {"language": "en", "next": english}
        )
        self.assertRedirects(response, english)
        self.assertEqual(response.cookies["django_language"].value, "en")
        self.assertContains(
            self.client.get(english), 'lang="en" id="htmlRoot" dir="ltr"'
        )
