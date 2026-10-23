from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from .views import _make_reset_token


class SecurityBoundaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "security@example.test", "security@example.test", "StrongTestOnly123!"
        )
        self.staff = User.objects.create_user("content", is_staff=True)
        self.client = APIClient()

    def test_login_and_signup_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        for endpoint in ("login", "signup"):
            response = client.post(
                f"/api/auth/{endpoint}/",
                {"email": self.user.email, "password": "StrongTestOnly123!"},
                HTTP_ORIGIN="https://foreign.example",
            )
            self.assertEqual(response.status_code, 403)
        client.get("/login/")
        response = client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": "StrongTestOnly123!"},
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)

    def test_old_access_and_refresh_invalid_after_password_change(self):
        token = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        response = self.client.post(
            "/api/auth/change-password/",
            {
                "current_password": "StrongTestOnly123!",
                "new_password": "AnotherStrong123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                "/api/auth/token/refresh/", {"refresh": str(token)}
            ).status_code,
            401,
        )

    def test_content_staff_cannot_manage_users(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="change_event"))
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/events/admin/events/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/admin/users/").status_code, 403)
        self.assertEqual(
            self.client.delete(f"/api/auth/admin/users/{self.user.pk}/").status_code,
            403,
        )
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_current_user_exposes_own_stable_identity_for_local_recovery(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.user.pk)
        self.assertNotIn("password", response.data)

    def test_unprivileged_staff_cannot_manage_content(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get("/api/events/admin/events/").status_code, 403)

    def test_invalid_favorite_id_is_validation_error(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(
            self.client.post(
                "/api/events/favorites/", {"event_id": "invalid"}
            ).status_code,
            400,
        )

    def test_user_values_are_not_interpolated_into_inline_javascript(self):
        source = (Path(settings.BASE_DIR) / "templates/admin.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("onclick=\"confirmDelete('event'", source)
        self.assertNotIn("onclick=\"confirmDelete('user'", source)

    def test_password_reset_revokes_old_access_and_refresh(self):
        token = RefreshToken.for_user(self.user)
        reset = _make_reset_token(self.user)
        response = self.client.post(
            f"/reset-password/{reset}/",
            {"password1": "NewSyntheticPass123!", "password2": "NewSyntheticPass123!"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 302)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                "/api/auth/token/refresh/", {"refresh": str(token)}
            ).status_code,
            401,
        )

    def test_case_insensitive_email_login_creates_matching_browser_session(self):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.user.email.upper(), "password": "StrongTestOnly123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_case_variant_signup_cannot_duplicate_email(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "email": self.user.email.upper(),
                "password": "StrongTestOnly123!",
                "password2": "StrongTestOnly123!",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_non_object_json_is_rejected_before_endpoint_processing(self):
        self.client.force_authenticate(self.user)
        for url in (
            "/api/events/favorites/",
            "/api/trips/preview/",
            "/api/daily-plan/generate/",
        ):
            response = self.client.post(url, [], format="json")
            self.assertEqual(response.status_code, 400)
