"""Validated, review-first synchronization; empty/error results never remove data."""

from datetime import timedelta
import json

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import CatalogSource, ContentAuditLog, Event, SourceRecord, SyncRun
from .providers import ADAPTERS, ProviderBlocked, ProviderError
from .serializers import EventSerializer


def audit(actor, action, event, before=None, after=None):
    return ContentAuditLog.objects.create(
        actor=actor,
        action=action,
        target=f"event:{event.pk}",
        before=before or {},
        after=after or {},
    )


def clean_record(record):
    if not isinstance(record, dict):
        raise serializers.ValidationError("Provider record must be an object.")
    external_id = serializers.CharField(max_length=100).run_validation(
        record.get("external_id")
    )
    allowed = {
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
        "rating",
        "latitude",
        "longitude",
        "opening_hours_text",
        "source",
        "source_url",
        "source_license",
    }
    payload = {key: value for key, value in record.items() if key in allowed}
    if record.get("category") == "events" and not (
        record.get("date") or record.get("start_date")
    ):
        raise serializers.ValidationError(
            "An event needs a real date from its provider."
        )
    uses_catalog_timestamp = (
        "date" not in payload and payload.get("category") != "events"
    )
    payload.setdefault("date", payload.get("start_date") or timezone.now().isoformat())
    validator = EventSerializer(data=payload)
    validator.is_valid(raise_exception=True)
    cleaned = json.loads(json.dumps(validator.validated_data, cls=DjangoJSONEncoder))
    if uses_catalog_timestamp:
        # Event.date is a required legacy record timestamp for evergreen places,
        # not a claimed opening/visit date. Never manufacture event schedules.
        cleaned.pop("date", None)
    return external_id, cleaned


@transaction.atomic
def _start_sync(source_id):
    source = CatalogSource.objects.select_for_update().get(pk=source_id)
    now = timezone.now()
    if source.lease_until and source.lease_until > now:
        raise ProviderBlocked("A synchronization is already running.")
    if source.next_sync_at and source.next_sync_at > now:
        raise ProviderBlocked(
            "Not due yet. Public providers are synchronized at most once per day."
        )
    source.last_attempt_at = now
    source.next_sync_at = now + timedelta(hours=max(24, source.interval_hours))
    source.lease_until = now + timedelta(minutes=5)
    source.save()
    return source, SyncRun.objects.create(source=source)


def sync_source(source_id):
    configured_source = CatalogSource.objects.get(pk=source_id)
    if not configured_source.enabled or not getattr(
        settings, "CATALOG_SYNC_ENABLED", False
    ):
        now = timezone.now()
        CatalogSource.objects.filter(pk=source_id).update(last_attempt_at=now)
        return SyncRun.objects.create(
            source=configured_source,
            status="blocked",
            finished_at=now,
            error="Synchronization is disabled. Enable the source and CATALOG_SYNC_ENABLED after reviewing its license and usage policy.",
        )
    source, run = _start_sync(source_id)
    try:
        if not source.enabled or not getattr(settings, "CATALOG_SYNC_ENABLED", False):
            raise ProviderBlocked(
                "Synchronization is disabled. Enable the source and CATALOG_SYNC_ENABLED after reviewing its license and usage policy."
            )
        if source.provider not in ADAPTERS:
            raise ProviderBlocked("No supported adapter for this source.")
        records = ADAPTERS[source.provider]()
        if not isinstance(records, list) or len(records) > 1000:
            raise ProviderError("Unexpected provider result size or type.")
        validated = {}
        for record in records:
            external_id, payload = clean_record(record)
            if external_id in validated and validated[external_id] != payload:
                raise ProviderError("Conflicting duplicate provider identifiers.")
            validated[external_id] = payload
        queued = 0
        with transaction.atomic():
            for external_id, payload in validated.items():
                existing = (
                    SourceRecord.objects.select_for_update()
                    .filter(source=source, external_id=external_id)
                    .first()
                )
                if existing is None:
                    # Match only an unambiguous title and position. All content
                    # still needs a human review before publication or update.
                    matches = Event.objects.filter(title__iexact=payload["title"])
                    if (
                        payload.get("latitude") is not None
                        and payload.get("longitude") is not None
                    ):
                        matches = matches.filter(
                            latitude__range=(
                                payload["latitude"] - 0.0005,
                                payload["latitude"] + 0.0005,
                            ),
                            longitude__range=(
                                payload["longitude"] - 0.0005,
                                payload["longitude"] + 0.0005,
                            ),
                        )
                    else:
                        matches = Event.objects.none()
                    event = matches.first() if matches.count() == 1 else None
                    SourceRecord.objects.create(
                        source=source,
                        external_id=external_id,
                        event=event,
                        payload=payload,
                    )
                    queued += 1
                else:
                    if existing.payload != payload:
                        existing.payload = payload
                        existing.status = "pending"
                        queued += 1
                    existing.last_seen_at = timezone.now()
                    existing.save()
        run.received = len(records)
        run.queued = queued
        run.status = "success" if records else "empty"
    except ProviderBlocked as exc:
        run.status = "blocked"
        run.error = str(exc)
        # Missing configuration performs no network request and consumes no quota.
        CatalogSource.objects.filter(pk=source_id).update(next_sync_at=None)
    except (ProviderError, serializers.ValidationError):
        run.status = "failed"
        run.error = "Provider failed or supplied invalid data. Existing catalogue and published content are unchanged. Review adapter configuration and try when due."
    except Exception:
        run.status = "failed"
        run.error = "Synchronization failed. Existing catalogue preserved."
    finally:
        run.finished_at = timezone.now()
        run.save()
        CatalogSource.objects.filter(pk=source_id).update(lease_until=None)
    return run


@transaction.atomic
def review_record(record_id, actor, approve, expected_seen_at=None):
    if (
        not actor
        or not actor.is_active
        or not actor.is_staff
        or not (actor.is_superuser or actor.has_perm("events.change_event"))
    ):
        raise PermissionDenied("Content review permission is required.")
    record = (
        SourceRecord.objects.select_for_update(of=("self",))
        .select_related("event")
        .get(pk=record_id)
    )
    if record.status != "pending":
        raise serializers.ValidationError("This record has already been reviewed.")
    if expected_seen_at and record.last_seen_at.isoformat() != expected_seen_at:
        raise serializers.ValidationError(
            "The source changed after this review was opened. Reload it."
        )
    if approve:
        before = EventSerializer(record.event).data if record.event else {}
        payload = {
            **record.payload,
            "is_active": True,
            "publication_status": "published",
        }
        if record.event:
            # Unknown source values never erase facts maintained by a curator.
            # Clearing known information remains an explicit manual edit.
            payload = {
                key: value
                for key, value in payload.items()
                if value is not None and value != ""
            }
        if not record.event:
            payload.setdefault("date", timezone.now().isoformat())
        serializer = EventSerializer(
            record.event, data=payload, partial=bool(record.event)
        )
        serializer.is_valid(raise_exception=True)
        record.event = serializer.save(last_verified_at=timezone.now())
        audit(
            actor,
            "source.approve",
            record.event,
            before,
            EventSerializer(record.event).data,
        )
        record.status = "approved"
    else:
        record.status = "rejected"
        ContentAuditLog.objects.create(
            actor=actor,
            action="source.reject",
            target=f"source-record:{record.pk}",
            before={"status": "pending"},
            after={"status": "rejected"},
        )
    record.reviewed_by = actor
    record.reviewed_at = timezone.now()
    record.save()
    return record
