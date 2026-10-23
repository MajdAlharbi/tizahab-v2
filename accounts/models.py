from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class UserPreferences(models.Model):
    LANGUAGE_CHOICES = [
        ("ar", "Arabic"),
        ("en", "English"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="preferences"
    )

    preferred_language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default="en",
    )

    budget_min = models.PositiveIntegerField(null=True, blank=True)

    budget_max = models.PositiveIntegerField(null=True, blank=True)

    interests = models.JSONField(default=list, blank=True)

    min_rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Minimum place rating (e.g. 3.5, 4.0, 4.5). Null means no filter.",
    )

    trip_duration = models.PositiveIntegerField(
        default=1,
        help_text="Number of trip days (1-30). Used by multi-day plan generation.",
    )

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user}"
