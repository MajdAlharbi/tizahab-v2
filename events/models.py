from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone

from .categories import (
    TOURISM_CATEGORY_CHOICES,
    TOURISM_CATEGORY_VALUES,
    normalize_category,
)


User = get_user_model()


class Event(models.Model):
    AREA_CHOICES = [
        ("Central Riyadh", "Central Riyadh"),
        ("North Riyadh", "North Riyadh"),
        ("East Riyadh", "East Riyadh"),
        ("South Riyadh", "South Riyadh"),
        ("West Riyadh", "West Riyadh"),
    ]
    CATEGORY_CHOICES = TOURISM_CATEGORY_CHOICES
    CATEGORY_VALUES = TOURISM_CATEGORY_VALUES
    CATEGORY_MAP = {
        "fast_food": "food",
        "restaurant": "food",
        "dessert": "food",
        "juice": "food",
        "bakery": "food",
        "shopping": "shopping",
        "other": "other",
    }

    title = models.CharField(max_length=255, db_index=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, db_index=True)
    description = models.TextField(blank=True)
    date = models.DateTimeField(db_index=True)
    start_date = models.DateTimeField(null=True, blank=True, db_index=True)
    end_date = models.DateTimeField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255)
    area = models.CharField(
        max_length=50,
        choices=AREA_CHOICES,
        default="Central Riyadh",
        db_index=True,
    )
    price_range = models.CharField(max_length=100, null=True, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    latitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    image_url = models.URLField(max_length=500, blank=True, default="")
    source = models.CharField(max_length=255, blank=True, default="")
    source_url = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    tourism_relevance = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Simple tourism relevance score from 1 to 5.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    opening_hours_text = models.CharField(max_length=500, blank=True, default="")
    source_license = models.CharField(max_length=120, blank=True, default="")
    last_verified_at = models.DateTimeField(null=True, blank=True)
    publication_status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("review", "In review"),
            ("published", "Published"),
        ],
        default="published",
        db_index=True,
    )

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["category", "date"]),
            models.Index(fields=["area", "category"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.publication_status != "published":
            self.is_active = False
        self.category = normalize_category(
            self.category,
            title=self.title,
            description=self.description,
        )
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        start = self.start_date or self.date
        if start and self.end_date and start > self.end_date:
            raise ValidationError(
                {"end_date": "End date must be on or after the start date."}
            )

    @property
    def primary_date(self):
        return (
            timezone.localtime(self.start_date).date()
            if self.start_date
            else timezone.localtime(self.date).date()
        )

    def availability_window(self):
        start = (
            timezone.localtime(self.start_date).date()
            if self.start_date
            else timezone.localtime(self.date).date()
        )
        end = timezone.localtime(self.end_date).date() if self.end_date else start
        return start, end

    def occurs_on(self, target_date):
        if not self.is_active:
            return False
        if not self.start_date and not self.end_date and self.category != "events":
            return True
        start, end = self.availability_window()
        return start <= target_date <= end

    def is_available_on(self, target_date):
        return self.occurs_on(target_date)


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "event"]]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}:{self.event_id}"


class CatalogSource(models.Model):
    provider = models.CharField(
        max_length=30,
        unique=True,
        choices=[
            ("osm", "OpenStreetMap"),
            ("ticketmaster", "Ticketmaster (access/storage verification required)"),
        ],
    )
    enabled = models.BooleanField(default=False)
    interval_hours = models.PositiveSmallIntegerField(
        default=24, validators=[MinValueValidator(24)]
    )
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_sync_at = models.DateTimeField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.provider


class SyncRun(models.Model):
    source = models.ForeignKey(
        CatalogSource, on_delete=models.PROTECT, related_name="runs"
    )
    status = models.CharField(
        max_length=20,
        default="running",
        choices=[
            ("running", "Running"),
            ("success", "Success"),
            ("empty", "Empty response (no removal)"),
            ("failed", "Failed"),
            ("blocked", "Blocked"),
        ],
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    received = models.PositiveIntegerField(default=0)
    queued = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-started_at"]


class SourceRecord(models.Model):
    source = models.ForeignKey(
        CatalogSource, on_delete=models.PROTECT, related_name="records"
    )
    external_id = models.CharField(max_length=100)
    event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="source_records",
    )
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
        db_index=True,
    )
    last_seen_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_provider_record"
            )
        ]

    def __str__(self):
        return f"{self.source}:{self.external_id}"


class ContentAuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=50)
    target = models.CharField(max_length=150)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
