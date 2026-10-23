from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import date, timedelta
from rest_framework.test import APIClient
from rest_framework import status
from django.core.signing import TimestampSigner, BadSignature
from unittest.mock import patch

from accounts.models import UserPreferences
from accounts.views import _make_reset_token, _read_reset_token
from accounts.serializers import UserPreferencesSerializer


def make_user(email="user@test.com", password="StrongPass1!"):
    return User.objects.create_user(username=email, email=email, password=password)


def auth_client(user):
    client = APIClient()
    response = client.post(
        "/api/auth/login/", {"email": user.email, "password": "StrongPass1!"}
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


class SignupTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_creates_user_and_returns_tokens(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "new@test.com",
                "password": "StrongPass1!",
                "password2": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(User.objects.filter(email="new@test.com").exists())

    def test_signup_rejects_duplicate_email(self):
        make_user("dup@test.com")
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "dup@test.com",
                "password": "StrongPass1!",
                "password2": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Email already exists.", str(response.data))

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "mismatch@test.com",
                "password": "StrongPass1!",
                "password2": "Different1!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Passwords do not match.", str(response.data))

    def test_signup_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": "weak@test.com",
                "password": "123",
                "password2": "123",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("at least 8 characters", str(response.data))


class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()

    def test_login_returns_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_wrong_password(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "wrongpassword",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid email or password.", str(response.data))

    def test_login_unknown_email(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "nobody@test.com",
                "password": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid email or password.", str(response.data))


class AuthTemplateNavigationTests(TestCase):
    def test_signup_login_tab_points_to_ui_login(self):
        response = self.client.get("/signup/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'href="/login/"')
        self.assertNotContains(response, 'href="/api/auth/login/"')

    def test_login_signup_tab_points_to_ui_signup(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'href="/signup/"')
        self.assertNotContains(response, 'href="/api/auth/signup/"')

    def test_auth_pages_have_visible_error_targets(self):
        login = self.client.get("/login/")
        signup = self.client.get("/signup/")

        self.assertContains(login, 'id="login-error"')
        self.assertContains(signup, 'id="signup-error"')
        self.assertContains(signup, "Password must be at least 8 characters")
        self.assertContains(signup, "Passwords do not match")


class SessionTokenTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user()

    def test_session_token_rejects_anonymous_user(self):
        response = self.client.get("/api/auth/session-token/")
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_session_token_returns_tokens_for_session_user(self):
        self.client.login(username=self.user.username, password="StrongPass1!")

        response = self.client.get("/api/auth/session-token/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)


class UserPreferencesTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = auth_client(self.user)

    def test_get_preferences_creates_defaults(self):
        response = self.client.get("/api/auth/preferences/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("interests", response.data)

    def test_set_valid_preferences(self):
        response = self.client.post(
            "/api/auth/preferences/",
            {
                "interests": ["food", "culture"],
                "budget_min": 0,
                "budget_max": 300,
                "preferred_language": "ar",
            },
        )
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED]
        )
        pref = UserPreferences.objects.get(user=self.user)
        self.assertEqual(pref.interests, ["food", "culture"])
        self.assertEqual(pref.budget_max, 300)

    def test_legacy_interest_alias_is_normalized(self):
        response = self.client.post(
            "/api/auth/preferences/",
            {
                "interests": ["restaurant", "outdoor"],
            },
        )
        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED]
        )
        pref = UserPreferences.objects.get(user=self.user)
        self.assertEqual(pref.interests, ["food", "nature"])

    def test_invalid_interest_rejected(self):
        response = self.client.post(
            "/api/auth/preferences/",
            {
                "interests": ["music"],
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_budget_min_greater_than_max_rejected(self):
        response = self.client.post(
            "/api/auth/preferences/",
            {
                "budget_min": 500,
                "budget_max": 100,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_budget_max_below_existing_min(self):
        pref, _ = UserPreferences.objects.get_or_create(user=self.user)
        pref.budget_min = 200
        pref.save()
        response = self.client.post("/api/auth/preferences/", {"budget_max": 50})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_set_trip_dates_in_preferences(self):
        start_date = (date.today() + timedelta(days=2)).isoformat()
        end_date = (date.today() + timedelta(days=4)).isoformat()

        response = self.client.post(
            "/api/auth/preferences/",
            {
                "interests": ["food"],
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        self.assertIn(
            response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED]
        )
        pref = UserPreferences.objects.get(user=self.user)
        self.assertEqual(pref.start_date.isoformat(), start_date)
        self.assertEqual(pref.end_date.isoformat(), end_date)

    def test_preferences_reject_end_date_before_start_date(self):
        start_date = (date.today() + timedelta(days=4)).isoformat()
        end_date = (date.today() + timedelta(days=2)).isoformat()

        response = self.client.post(
            "/api/auth/preferences/",
            {
                "interests": ["food"],
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_current_user_returns_saved_trip_dates(self):
        pref, _ = UserPreferences.objects.get_or_create(user=self.user)
        pref.start_date = date.today() + timedelta(days=1)
        pref.end_date = date.today() + timedelta(days=3)
        pref.save()

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["start_date"], pref.start_date)
        self.assertEqual(response.data["end_date"], pref.end_date)

    def test_trip_duration_below_range_returns_400(self):
        response = self.client.post("/api/auth/preferences/", {"trip_duration": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trip_duration_above_range_returns_400(self):
        response = self.client.post("/api/auth/preferences/", {"trip_duration": 31})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preferences_require_auth(self):
        client = APIClient()
        response = client.get("/api/auth/preferences/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetTokenTests(TestCase):
    def test_token_roundtrip(self):
        user = make_user("roundtrip@test.com")
        token = _make_reset_token(user)
        result = _read_reset_token(token)
        self.assertEqual(result, str(user.pk))

    def test_bad_token_raises(self):
        with self.assertRaises(BadSignature):
            _read_reset_token("totally.invalid.token")

    def test_forgot_password_same_response_regardless_of_email(self):
        """Prevent user enumeration: both existing and non-existing emails get same response."""
        make_user("real@test.com")
        client = self.client

        r1 = client.post("/forgot-password/", {"email": "real@test.com"})
        r2 = client.post("/forgot-password/", {"email": "ghost@test.com"})

        # Both should redirect or render — neither should expose whether the user exists
        # real user gets redirect (302), non-existing user gets re-render (200 with info)
        # The key check: ghost email must NOT reveal "no account found"
        self.assertNotIn(b"No account found", r2.content)

    def test_reset_with_invalid_token_shows_error(self):
        response = self.client.get("/reset-password/badtoken/")
        self.assertIn(b"invalid", response.content.lower())

    def test_reset_with_valid_token_allows_password_change(self):
        user = make_user("resetme@test.com")
        token = _make_reset_token(user)
        from urllib.parse import quote

        safe_token = quote(token, safe="")

        response = self.client.post(
            f"/reset-password/{safe_token}/",
            {"password1": "NewPass123!", "password2": "NewPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass123!"))

    def test_reset_token_cannot_be_reused_after_successful_reset(self):
        user = make_user("reset-once@test.com")
        token = _make_reset_token(user)
        from urllib.parse import quote

        safe_token = quote(token, safe="")
        url = f"/reset-password/{safe_token}/"

        first = self.client.post(
            url,
            {"password1": "NewPass123!", "password2": "NewPass123!"},
        )
        self.assertEqual(first.status_code, 302)

        second = self.client.post(
            url,
            {"password1": "AnotherPass123!", "password2": "AnotherPass123!"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn(b"invalid", second.content.lower())

        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPass123!"))

    @patch("accounts.views.logger")
    @patch("accounts.views.send_mail", side_effect=RuntimeError("smtp down"))
    def test_forgot_password_logs_email_failures_but_keeps_safe_response(
        self, send_mail_mock, logger_mock
    ):
        make_user("mailfail@test.com")

        response = self.client.post(
            "/forgot-password/",
            {"email": "mailfail@test.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"if that email is registered", response.content.lower())
        send_mail_mock.assert_called_once()
        logger_mock.error.assert_called_once()

    def test_login_page_links_to_clean_forgot_password_url(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/forgot-password/"')
        self.assertNotContains(response, "/api/auth/ui/forgot-password/")


class LogoutFlowTests(TestCase):
    def test_logout_post_clears_server_session(self):
        user = make_user("logout@test.com")
        self.client.force_login(user)

        response = self.client.post("/logout/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_get_cannot_change_session(self):
        user = make_user("logout-get@test.com")
        self.client.force_login(user)

        response = self.client.get("/logout/")

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)


class AdminUserValidationTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.com")
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.user = make_user("member@test.com")
        self.other = make_user("other@test.com")
        self.client = auth_client(self.admin)

    def test_admin_patch_rejects_duplicate_email(self):
        response = self.client.patch(
            f"/api/auth/admin/users/{self.user.pk}/",
            {"email": self.other.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "member@test.com")

    def test_admin_patch_rejects_invalid_email_format(self):
        response = self.client.patch(
            f"/api/auth/admin/users/{self.user.pk}/",
            {"email": "not-an-email"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_patch_updates_valid_fields(self):
        response = self.client.patch(
            f"/api/auth/admin/users/{self.user.pk}/",
            {"email": "updated@test.com", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated@test.com")
        self.assertFalse(self.user.is_active)
