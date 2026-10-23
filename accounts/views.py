from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.contrib.auth import (
    login as django_login,
    logout as django_logout,
)
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django_ratelimit.core import is_ratelimited
import logging

from .models import UserPreferences
from .permissions import IsSuperAdmin
from .serializers import (
    UserPreferencesSerializer,
    SignupSerializer,
    LoginSerializer,
    AdminUserUpdateSerializer,
)
from .throttles import (
    ChangePasswordRateThrottle,
    LoginRateThrottle,
    SignupRateThrottle,
)
from events.categories import normalize_category_input

User = get_user_model()
logger = logging.getLogger(__name__)

_RESET_SALT = "tizahab-password-reset"
_RESET_MAX_AGE = 3600  # 1 hour


def _make_reset_token(user):
    signer = TimestampSigner(salt=_RESET_SALT)
    reset_token = default_token_generator.make_token(user)
    return signer.sign(f"{user.pk}:{reset_token}")


def _read_reset_token(token):
    """Return user_pk string or raise SignatureExpired / BadSignature."""
    signer = TimestampSigner(salt=_RESET_SALT)
    unsigned = signer.unsign(token, max_age=_RESET_MAX_AGE)
    try:
        user_pk, reset_token = unsigned.split(":", 1)
        user = User.objects.get(pk=user_pk)
    except (ValueError, User.DoesNotExist):
        raise BadSignature("Invalid reset token")

    if not default_token_generator.check_token(user, reset_token):
        raise BadSignature("Invalid or already-used reset token")

    return user_pk


def _api_rate_limited(request, rate, group):
    return is_ratelimited(
        request=request,
        group=group,
        key="ip",
        rate=rate,
        method="POST",
        increment=True,
    )


@ratelimit(key="ip", rate="5/m", block=True)
def login_page(request):
    return render(request, "login.html")


@ratelimit(key="ip", rate="5/m", block=True)
def signup_page(request):
    return render(request, "signup.html")


def preferences_page(request):
    return render(request, "preferences.html")


@require_POST
def logout_view(request):
    django_logout(request)
    return JsonResponse({"detail": "Logged out successfully."}, status=200)


@ratelimit(
    key="ip",
    rate=getattr(settings, "PASSWORD_RESET_RATE_LIMIT", "3/m"),
    block=True,
)
def forgot_password_page(request):
    if request.method == "POST":
        if _api_rate_limited(
            request,
            getattr(settings, "PASSWORD_RESET_RATE_LIMIT", "3/m"),
            "forgot_password_page",
        ):
            return render(
                request,
                "forgot_password.html",
                {"info": "Too many reset attempts. Please try again later."},
                status=429,
            )
        email = request.POST.get("email", "").strip()
        try:
            user = User.objects.get(email=email)
            token = _make_reset_token(user)
            from urllib.parse import quote

            safe_token = quote(token, safe="")
            reset_url = request.build_absolute_uri(f"/reset-password/{safe_token}/")
            try:
                send_mail(
                    subject="Reset your Tizahab password",
                    message=f"Click to reset your password: {reset_url}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception:
                logger.error(
                    "Password reset email failed for user_id=%s",
                    user.pk,
                    exc_info=True,
                )
        except User.DoesNotExist:
            pass

        return render(
            request,
            "forgot_password.html",
            {"info": "If that email is registered you will receive a reset link."},
        )

    return render(request, "forgot_password.html")


@ratelimit(
    key="ip",
    rate=getattr(settings, "PASSWORD_RESET_CONFIRM_RATE_LIMIT", "5/m"),
    method="POST",
    block=True,
)
def reset_password_page(request, token):
    from urllib.parse import unquote

    safe_token = unquote(token)

    try:
        user_pk = _read_reset_token(safe_token)
        user = User.objects.get(pk=user_pk)
    except (SignatureExpired, BadSignature, User.DoesNotExist, ValueError):
        return render(
            request,
            "reset_password.html",
            {"error": "This reset link is invalid or has expired."},
        )

    if request.method == "POST":
        if _api_rate_limited(
            request,
            getattr(settings, "PASSWORD_RESET_CONFIRM_RATE_LIMIT", "5/m"),
            "reset_password_page",
        ):
            return render(
                request,
                "reset_password.html",
                {"token": token, "error": "Too many attempts. Please try again later."},
                status=429,
            )
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if not password1:
            return render(
                request,
                "reset_password.html",
                {"token": token, "error": "Password cannot be empty."},
            )

        if password1 != password2:
            return render(
                request,
                "reset_password.html",
                {"token": token, "error": "Passwords do not match."},
            )

        try:
            validate_password(password1, user=user)
        except ValidationError as e:
            return render(
                request,
                "reset_password.html",
                {"token": token, "error": e.messages[0]},
            )

        user.set_password(password1)
        user.save()
        return redirect("/login/")

    return render(request, "reset_password.html", {"token": token})


class SignupAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SignupRateThrottle]

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        if _api_rate_limited(
            request,
            getattr(settings, "SIGNUP_RATE_LIMIT", "20/hour"),
            "signup_api",
        ):
            return Response(
                {"detail": "Request was throttled. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        django_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        if _api_rate_limited(
            request,
            getattr(settings, "LOGIN_RATE_LIMIT", "100/hour"),
            "login_api",
        ):
            return Response(
                {"detail": "Request was throttled. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        django_login(
            request,
            serializer.user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class SessionTokenAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        refresh = RefreshToken.for_user(request.user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        preferences, _ = UserPreferences.objects.get_or_create(user=request.user)
        serializer = UserPreferencesSerializer(preferences)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        preferences, created = UserPreferences.objects.get_or_create(user=request.user)
        serializer = UserPreferencesSerializer(
            preferences, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def put(self, request):
        return self.post(request)


class CurrentUserView(APIView):
    """GET /api/auth/me/ — returns the authenticated user's profile data."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        preferences, _ = UserPreferences.objects.get_or_create(user=user)
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "username": user.username,
                "full_name": user.get_full_name(),
                "is_superuser": user.is_superuser,
                "can_manage_content": user.is_staff
                and (user.is_superuser or user.has_perm("events.change_event")),
                "interests": [
                    normalize_category_input(value) or str(value).strip().lower()
                    for value in (preferences.interests or [])
                    if str(value).strip()
                ],
                "budget_min": preferences.budget_min,
                "budget_max": preferences.budget_max,
                "preferred_language": preferences.preferred_language,
                "min_rating": preferences.min_rating,
                "trip_duration": preferences.trip_duration or 1,
                "start_date": preferences.start_date,
                "end_date": preferences.end_date,
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ — change password for authenticated user."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ChangePasswordRateThrottle]

    def post(self, request):
        if _api_rate_limited(
            request,
            getattr(settings, "CHANGE_PASSWORD_RATE_LIMIT", "30/hour"),
            "change_password_api",
        ):
            return Response(
                {"detail": "Request was throttled. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")

        if not current_password or not new_password:
            return Response(
                {"detail": "Both current_password and new_password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if not user.check_password(current_password):
            return Response(
                {"detail": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response(
                {"detail": e.messages[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        return Response(
            {"detail": "Password updated successfully."},
            status=status.HTTP_200_OK,
        )


def admin_panel_view(request):
    return render(request, "admin.html")


class AdminUserListAPIView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        users = User.objects.annotate(
            plan_count=Count("trips", distinct=True)
        ).order_by("-date_joined")
        data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_staff": u.is_staff,
                "role": (
                    "Super Admin"
                    if u.is_superuser
                    else (
                        "Content Manager"
                        if u.is_staff and u.has_perm("events.change_event")
                        else "User"
                    )
                ),
                "is_active": u.is_active,
                "date_joined": u.date_joined.isoformat(),
                "plan_count": u.plan_count,
            }
            for u in users
        ]
        return Response(data)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request, pk):
        u = get_object_or_404(User, pk=pk)
        return Response(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_staff": u.is_staff,
                "is_active": u.is_active,
            }
        )

    def patch(self, request, pk):
        u = get_object_or_404(User, pk=pk)
        serializer = AdminUserUpdateSerializer(
            u,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        if u == request.user and serializer.validated_data.get("is_active") is False:
            return Response({"detail": "Cannot deactivate yourself."}, status=400)
        serializer.save()
        return Response(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
            }
        )

    def delete(self, request, pk):
        if str(pk) == str(request.user.pk):
            return Response(
                {"detail": "Cannot delete yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        u = get_object_or_404(User, pk=pk)
        # Deactivation preserves the account's private trips, favorites and plans.
        u.is_active = False
        u.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
