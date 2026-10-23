from rest_framework import serializers
import math
from .models import Event, Favorite
from .categories import (
    TOURISM_CATEGORY_VALUES,
    normalize_category,
    normalize_category_input,
)


class EventSerializer(serializers.ModelSerializer):
    def validate_latitude(self, value):
        if value is not None and not math.isfinite(value):
            raise serializers.ValidationError("Latitude must be finite.")
        return value

    def validate_longitude(self, value):
        if value is not None and not math.isfinite(value):
            raise serializers.ValidationError("Longitude must be finite.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["category"] = Event.CATEGORY_MAP.get(instance.category, instance.category)
        return data

    def validate_category(self, value):
        normalized = normalize_category_input(value)
        if normalized not in TOURISM_CATEGORY_VALUES:
            raise serializers.ValidationError(
                f"Invalid category. Valid options: {TOURISM_CATEGORY_VALUES}"
            )
        return normalized

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "category",
            "description",
            "date",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "location",
            "area",
            "price",
            "price_range",
            "latitude",
            "longitude",
            "rating",
            "image_url",
            "source",
            "source_url",
            "is_active",
            "tourism_relevance",
            "opening_hours_text",
            "source_license",
            "last_verified_at",
            "publication_status",
        ]
        read_only_fields = ["last_verified_at"]

    def validate(self, attrs):
        if (
            attrs.get(
                "publication_status",
                getattr(self.instance, "publication_status", "published"),
            )
            != "published"
        ):
            attrs["is_active"] = False
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        effective_start = start_date or attrs.get(
            "date", getattr(self.instance, "date", None)
        )
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))

        if effective_start and end_date and effective_start > end_date:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )

        if (
            start_time
            and end_time
            and start_time > end_time
            and (not start_date or not end_date or start_date.date() == end_date.date())
        ):
            raise serializers.ValidationError(
                {"end_time": "end_time must be on or after start_time."}
            )

        return attrs


class FavoriteSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "event", "created_at"]
