from django.contrib import admin, messages
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .catalog import audit, review_record
from .models import CatalogSource, ContentAuditLog, Event, SourceRecord, SyncRun
from .serializers import EventSerializer


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    search_fields = ("title", "description", "location", "source")
    readonly_fields = ("last_verified_at", "created_at", "updated_at")
    actions = ["deactivate_places", "publish_places"]
    list_display = (
        "title",
        "category",
        "publication_status",
        "is_active",
        "last_verified_at",
        "source",
    )
    list_filter = ("category", "publication_status", "is_active", "source_license")

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        before = EventSerializer(Event.objects.get(pk=obj.pk)).data if change else {}
        obj.last_verified_at = timezone.now()
        super().save_model(request, obj, form, change)
        audit(
            request.user,
            "admin.event.update" if change else "admin.event.create",
            obj,
            before,
            EventSerializer(obj).data,
        )

    @admin.action(description="Deactivate selected places (preserve saved trips)")
    def deactivate_places(self, request, queryset):
        for event in queryset:
            before = EventSerializer(event).data
            event.is_active = False
            event.save()
            audit(
                request.user,
                "admin.event.deactivate",
                event,
                before,
                EventSerializer(event).data,
            )

    @admin.action(description="Publish selected reviewed places")
    def publish_places(self, request, queryset):
        for event in queryset:
            before = EventSerializer(event).data
            event.publication_status = "published"
            event.is_active = True
            event.last_verified_at = timezone.now()
            event.full_clean()
            event.save()
            audit(
                request.user,
                "admin.event.publish",
                event,
                before,
                EventSerializer(event).data,
            )


@admin.register(SourceRecord)
class SourceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "external_id",
        "source",
        "event",
        "status",
        "last_seen_at",
        "reviewed_by",
    )
    list_filter = ("status", "source")
    search_fields = ("external_id", "event__title")
    readonly_fields = tuple(field.name for field in SourceRecord._meta.fields)
    actions = ["approve_records", "reject_records"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _review(self, request, queryset, approve):
        for record in queryset:
            try:
                review_record(record.pk, request.user, approve)
            except ValidationError:
                self.message_user(
                    request,
                    f"Record {record.pk} changed or could not be reviewed. Reload and inspect it.",
                    messages.WARNING,
                )

    @admin.action(description="Approve and publish selected source records")
    def approve_records(self, request, queryset):
        self._review(request, queryset, True)

    @admin.action(
        description="Reject selected changes (keep existing published content)"
    )
    def reject_records(self, request, queryset):
        self._review(request, queryset, False)


@admin.register(CatalogSource)
class CatalogSourceAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "enabled",
        "interval_hours",
        "last_attempt_at",
        "next_sync_at",
    )
    readonly_fields = ("provider", "last_attempt_at", "next_sync_at", "lease_until")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


class ImmutableLogAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SyncRun)
class SyncRunAdmin(ImmutableLogAdmin):
    list_display = ("source", "status", "started_at", "received", "queued", "error")
    list_filter = ("source", "status")


@admin.register(ContentAuditLog)
class ContentAuditLogAdmin(ImmutableLogAdmin):
    list_display = ("created_at", "actor", "action", "target")
    list_filter = ("action",)
