from rest_framework import serializers
from datetime import date
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserPreferences
from events.models import Event
from events.categories import normalize_category_input


class UserPreferencesSerializer(serializers.ModelSerializer):
    """
    Serializer for user preferences including language, budget, and interests.

    Validates:
    - budget_min <= budget_max
    - interests are valid event categories
    - budget values are non-negative
    """

    VALID_INTERESTS = Event.CATEGORY_VALUES

    class Meta:
        model = UserPreferences
        fields = [
            "preferred_language",
            "budget_min",
            "budget_max",
            "interests",
            "min_rating",
            "trip_duration",
            "start_date",
            "end_date",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["interests"] = [
            normalize_category_input(value) or str(value).strip().lower()
            for value in (data.get("interests") or [])
            if str(value).strip()
        ]
        return data

    def validate_trip_duration(self, value):
        """Require trip_duration to stay within the supported range."""
        if value is None:
            return 1
        if value < 1 or value > 30:
            raise serializers.ValidationError("trip_duration must be between 1 and 30.")
        return value

    def validate_interests(self, value):
        """Validate that interests only contain valid event categories."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Interests must be a list.")

        normalized_interests = [
            normalize_category_input(i) for i in value if str(i).strip()
        ]
        invalid_interests = [
            i for i in normalized_interests if i not in self.VALID_INTERESTS
        ]
        if invalid_interests:
            raise serializers.ValidationError(
                f"Invalid interests: {invalid_interests}. Valid options: {self.VALID_INTERESTS}"
            )

        return normalized_interests

    def validate_budget_min(self, value):
        """Validate budget_min is non-negative."""
        if value is not None and value < 0:
            raise serializers.ValidationError("Budget minimum cannot be negative.")
        return value

    def validate_budget_max(self, value):
        """Validate budget_max is non-negative."""
        if value is not None and value < 0:
            raise serializers.ValidationError("Budget maximum cannot be negative.")
        return value

    def validate_min_rating(self, value):
        if value is not None and not 0 <= value <= 5:
            raise serializers.ValidationError("min_rating must be between 0 and 5.")
        return value

    def validate(self, attrs):
        """Validate that budget_min <= budget_max, including against existing instance values."""
        instance = self.instance
        min_b = attrs.get(
            "budget_min", getattr(instance, "budget_min", None) if instance else None
        )
        max_b = attrs.get(
            "budget_max", getattr(instance, "budget_max", None) if instance else None
        )

        if min_b is not None and max_b is not None and min_b > max_b:
            raise serializers.ValidationError(
                "budget_min cannot be greater than budget_max"
            )

        start_date = attrs.get(
            "start_date", getattr(instance, "start_date", None) if instance else None
        )
        end_date = attrs.get(
            "end_date", getattr(instance, "end_date", None) if instance else None
        )
        dates_changed = "start_date" in attrs or "end_date" in attrs
        if dates_changed and start_date and start_date < date.today():
            raise serializers.ValidationError(
                {"start_date": "Cannot save a past start_date."}
            )
        if end_date and start_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        if start_date and end_date:
            duration = (end_date - start_date).days + 1
            if duration > 30:
                raise serializers.ValidationError(
                    {"end_date": "Trips cannot exceed 30 days."}
                )
            if "trip_duration" in attrs and attrs["trip_duration"] != duration:
                raise serializers.ValidationError(
                    {"trip_duration": "Must match the selected date range."}
                )
            attrs["trip_duration"] = duration

        return attrs


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    full_name = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "password", "password2", "full_name")

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop("password2")
        full_name = validated_data.pop("full_name", "").strip()
        email = validated_data["email"]

        user = User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
        )
        if full_name:
            parts = full_name.split(" ", 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ""
            user.save(update_fields=["first_name", "last_name"])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        try:
            user_obj = User.objects.get(email__iexact=email)
            username = user_obj.username
        except User.DoesNotExist:
            username = email
        except User.MultipleObjectsReturned:
            raise serializers.ValidationError("Invalid email or password.")

        user = authenticate(username=username, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        self.user = user

        refresh = RefreshToken.for_user(user)

        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = ("username", "email", "is_active")

    def validate_email(self, value):
        queryset = User.objects.exclude(pk=getattr(self.instance, "pk", None))
        value = value.strip().lower()
        if queryset.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_username(self, value):
        queryset = User.objects.exclude(pk=getattr(self.instance, "pk", None))
        if queryset.filter(username=value).exists():
            raise serializers.ValidationError(
                "A user with this username already exists."
            )
        return value
