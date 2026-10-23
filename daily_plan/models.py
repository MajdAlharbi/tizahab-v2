from django.db import models
from django.contrib.auth import get_user_model
from events.models import Event

User = get_user_model()


class DailyPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_plans")
    date = models.DateField()
    events = models.ManyToManyField(Event, related_name="daily_plans", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "date"]]

    def __str__(self):
        return f"{self.user} - {self.date}"


class DailyPlanItem(models.Model):
    SLOT_CHOICES = [
        ("breakfast", "Breakfast"),
        ("activity", "Activity"),
        ("lunch", "Lunch"),
        ("evening", "Evening"),
    ]

    SOURCE_CHOICES = [
        ("generated", "Generated"),
        ("manual", "Manual"),
        ("replacement", "Replacement"),
    ]

    plan = models.ForeignKey(
        DailyPlan,
        related_name="items",
        on_delete=models.CASCADE,
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    slot_type = models.CharField(max_length=20, choices=SLOT_CHOICES)
    order = models.PositiveIntegerField(default=0)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="generated",
    )
    locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "event"],
                name="unique_event_per_daily_plan_item",
            )
        ]

    def __str__(self):
        return f"{self.plan_id}:{self.slot_type}:{self.event_id}"


class Trip(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trips")
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    duration = models.PositiveSmallIntegerField(default=1)
    preferences = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    is_archived = models.BooleanField(default=False, db_index=True)
    legacy_plan = models.OneToOneField(
        DailyPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imported_trip",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration__gte=1, duration__lte=30),
                name="trip_duration_1_30",
            )
        ]

    def __str__(self):
        return self.name


class TripDay(models.Model):
    trip = models.ForeignKey(Trip, related_name="days", on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField()
    date = models.DateField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "position"], name="unique_trip_day_position"
            )
        ]


class TripActivity(models.Model):
    trip = models.ForeignKey(Trip, related_name="activities", on_delete=models.CASCADE)
    day = models.ForeignKey(
        TripDay,
        related_name="activities",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    event = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="trip_activities"
    )
    key = models.CharField(max_length=64)
    slot_type = models.CharField(
        max_length=20, choices=DailyPlanItem.SLOT_CHOICES, default="activity"
    )
    position = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=20, default="generated")
    locked = models.BooleanField(default=False)
    override_preferences = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "key"], name="unique_trip_activity_key"
            ),
            models.UniqueConstraint(
                fields=["day", "event"], name="unique_event_per_trip_day"
            ),
        ]
