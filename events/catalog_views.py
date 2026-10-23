from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanManageContent
from .catalog import review_record, sync_source
from .models import CatalogSource, ContentAuditLog, SourceRecord
from .providers import ProviderBlocked
from .serializers import EventSerializer
from .views import EventListPagination


def record_data(record):
    return {
        "id": record.pk,
        "source": record.source.provider,
        "external_id": record.external_id,
        "status": record.status,
        "payload": record.payload,
        "event_id": record.event_id,
        "current": EventSerializer(record.event).data if record.event else None,
        "last_seen_at": record.last_seen_at.isoformat(),
    }


class ReviewQueueAPIView(APIView):
    permission_classes = [CanManageContent]

    def get(self, request):
        records = (
            SourceRecord.objects.filter(status="pending")
            .select_related("source", "event")
            .order_by("pk")
        )
        paginator = EventListPagination()
        page = paginator.paginate_queryset(records, request, view=self)
        return paginator.get_paginated_response(
            [record_data(record) for record in page]
        )


class ReviewDecisionAPIView(APIView):
    permission_classes = [CanManageContent]

    def post(self, request, pk):
        get_object_or_404(SourceRecord, pk=pk)
        decision = serializers.ChoiceField(
            choices=["approve", "reject"]
        ).run_validation(request.data.get("decision"))
        seen_at = serializers.CharField(max_length=50).run_validation(
            request.data.get("last_seen_at")
        )
        record = review_record(pk, request.user, decision == "approve", seen_at)
        return Response(record_data(record))


class CatalogSourcesAPIView(APIView):
    permission_classes = [CanManageContent]

    def get(self, request):
        result = []
        for source in CatalogSource.objects.all().order_by("pk"):
            run = source.runs.first()
            result.append(
                {
                    "id": source.pk,
                    "provider": source.provider,
                    "enabled": source.enabled,
                    "interval_hours": source.interval_hours,
                    "last_attempt_at": source.last_attempt_at,
                    "next_sync_at": source.next_sync_at,
                    "last_run": (
                        {
                            "status": run.status,
                            "error": run.error,
                            "received": run.received,
                            "queued": run.queued,
                            "finished_at": run.finished_at,
                        }
                        if run
                        else None
                    ),
                }
            )
        return Response(result)


class CatalogSyncAPIView(APIView):
    permission_classes = [CanManageContent]

    def post(self, request, pk):
        get_object_or_404(CatalogSource, pk=pk)
        try:
            run = sync_source(pk)
        except ProviderBlocked as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(
            {
                "status": run.status,
                "received": run.received,
                "queued": run.queued,
                "detail": run.error
                or "Sync complete. Review new and changed records before publishing.",
            },
            status=(
                503
                if run.status == "failed"
                else 409 if run.status == "blocked" else 200
            ),
        )


class ContentAuditAPIView(APIView):
    permission_classes = [CanManageContent]

    def get(self, request):
        paginator = EventListPagination()
        page = paginator.paginate_queryset(
            ContentAuditLog.objects.select_related("actor").all(), request, view=self
        )
        return paginator.get_paginated_response(
            [
                {
                    "id": log.pk,
                    "actor": log.actor.get_username() if log.actor else None,
                    "action": log.action,
                    "target": log.target,
                    "created_at": log.created_at,
                    "before": log.before,
                    "after": log.after,
                }
                for log in page
            ]
        )
