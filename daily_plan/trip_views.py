from django.shortcuts import get_object_or_404, render
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import Trip
from .trip_services import (
    generate_document,
    preview_dates,
    save_document,
    trip_document,
    validate_document,
)


def trips_page(request):
    return render(request, "trips.html")


class PreviewThrottle(AnonRateThrottle):
    rate = "60/hour"


class TripPreviewAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PreviewThrottle]

    def post(self, request):
        raw = request.data.get("trip", {})
        action = request.data.get("action", "generate")
        confirmed = serializers.BooleanField().run_validation(
            request.data.get("confirmed", False)
        )
        if action == "generate":
            result = generate_document(
                raw, day_index=request.data.get("day_index"), confirmed=confirmed
            )
        elif action == "dates":
            result = preview_dates(
                raw,
                request.data.get("start_date"),
                request.data.get("duration"),
                confirmed,
            )
        elif action == "validate":
            result = {"trip": validate_document(raw, allow_historical=True)}
        else:
            raise serializers.ValidationError({"action": "Unknown trip action."})
        return Response(result)


class TripListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            list(
                Trip.objects.filter(
                    user=request.user,
                    is_archived=request.query_params.get("archived") == "1",
                ).values(
                    "id",
                    "name",
                    "start_date",
                    "duration",
                    "revision",
                    "updated_at",
                    "is_archived",
                )
            )
        )

    def post(self, request):
        trip = save_document(request.user, request.data)
        return Response(trip_document(trip), status=201)


class TripDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(
            trip_document(get_object_or_404(Trip, pk=pk, user=request.user))
        )

    @transaction.atomic
    def _set_archived(self, request, pk, archived):
        trip = get_object_or_404(
            Trip.objects.select_for_update(), pk=pk, user=request.user
        )
        if not serializers.BooleanField().run_validation(
            request.data.get("confirmed", False)
        ):
            raise serializers.ValidationError(
                {"confirmation": "Confirm this change first."}
            )
        revision = serializers.IntegerField(min_value=1).run_validation(
            request.data.get("revision")
        )
        if revision != trip.revision:
            return Response(
                {"conflict": "This trip changed. Reopen it before trying again."},
                status=409,
            )
        trip.is_archived = archived
        trip.revision += 1
        trip.save(update_fields=["is_archived", "revision", "updated_at"])
        return Response(trip_document(trip))

    def delete(self, request, pk):
        # Reversible removal from the collection. Activities and legacy links stay.
        return self._set_archived(request, pk, True)

    def patch(self, request, pk):
        if request.data.get("action") != "restore":
            raise serializers.ValidationError({"action": "Only restore is supported."})
        return self._set_archived(request, pk, False)

    def put(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk, user=request.user)
        try:
            trip = save_document(
                request.user,
                request.data,
                trip=trip,
                confirmed=serializers.BooleanField().run_validation(
                    request.data.get("confirmed", False)
                ),
            )
        except serializers.ValidationError as exc:
            if isinstance(exc.detail, dict) and "conflict" in exc.detail:
                return Response(exc.detail, status=409)
            raise
        return Response(trip_document(trip))
