from django.urls import path
from .views import (
    SignupAPIView,
    LoginAPIView,
    SessionTokenAPIView,
    UserPreferencesView,
    CurrentUserView,
    ChangePasswordView,
    AdminUserListAPIView,
    AdminUserDetailAPIView,
    login_page,
    signup_page,
    preferences_page,
    forgot_password_page,
    reset_password_page,
)

urlpatterns = [
    # API endpoints
    path("signup/", SignupAPIView.as_view(), name="api-signup"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("session-token/", SessionTokenAPIView.as_view(), name="session-token"),
    path("preferences/", UserPreferencesView.as_view(), name="user-preferences"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    # Admin user management
    path("admin/users/", AdminUserListAPIView.as_view(), name="admin-user-list"),
    path(
        "admin/users/<int:pk>/",
        AdminUserDetailAPIView.as_view(),
        name="admin-user-detail",
    ),
    # UI pages
    path("ui/login/", login_page, name="login-page"),
    path("ui/signup/", signup_page, name="signup-page"),
    path("ui/preferences/", preferences_page, name="preferences-page"),
    path("ui/forgot-password/", forgot_password_page, name="forgot-password"),
    path("ui/reset-password/<str:token>/", reset_password_page, name="reset-password"),
]
