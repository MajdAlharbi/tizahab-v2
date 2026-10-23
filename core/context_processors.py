from django.conf import settings
from django.urls import translate_url


def google_maps_api_key(request):
    return {
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_PLACES_API_KEY": getattr(settings, "GOOGLE_PLACES_API_KEY", ""),
        "GOOGLE_BROWSER_MAPS_API_KEY": getattr(
            settings,
            "GOOGLE_BROWSER_MAPS_API_KEY",
            "",
        ),
    }


def language_switch_next(request):
    # The unprefixed set_language endpoint resolves URLs in the default language.
    return {
        "social_google_enabled": bool(
            getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", "")
            and getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET", "")
        ),
        "social_facebook_enabled": bool(
            getattr(settings, "SOCIAL_AUTH_FACEBOOK_KEY", "")
            and getattr(settings, "SOCIAL_AUTH_FACEBOOK_SECRET", "")
        ),
        "language_switch_next": translate_url(
            request.get_full_path(), settings.LANGUAGE_CODE
        ),
    }
