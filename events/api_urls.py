from django.urls import path
from .views import (
    EventListAPIView,
    EventRetrieveAPIView,
    FilteredEventsAPIView,
    FavoriteListCreateAPIView,
    FavoriteBulkCreateAPIView,
    FavoriteDeleteAPIView,
    AdminEventListCreateAPIView,
    AdminEventRetrieveUpdateDestroyAPIView,
    AdminDashboardStatsAPIView,
)
from .catalog_views import (
    ReviewQueueAPIView,
    ReviewDecisionAPIView,
    CatalogSourcesAPIView,
    CatalogSyncAPIView,
    ContentAuditAPIView,
)

urlpatterns = [
    path("admin/review/", ReviewQueueAPIView.as_view(), name="catalog-review"),
    path(
        "admin/review/<int:pk>/",
        ReviewDecisionAPIView.as_view(),
        name="catalog-review-decision",
    ),
    path("admin/sources/", CatalogSourcesAPIView.as_view(), name="catalog-sources"),
    path(
        "admin/sources/<int:pk>/sync/",
        CatalogSyncAPIView.as_view(),
        name="catalog-sync",
    ),
    path("admin/audit/", ContentAuditAPIView.as_view(), name="content-audit"),
    path("", EventListAPIView.as_view(), name="event-list"),
    path("filtered/", FilteredEventsAPIView.as_view(), name="event-filtered"),
    path(
        "favorites/", FavoriteListCreateAPIView.as_view(), name="favorites-list-create"
    ),
    path(
        "favorites/bulk/",
        FavoriteBulkCreateAPIView.as_view(),
        name="favorites-bulk-create",
    ),
    path(
        "favorites/<int:event_id>/",
        FavoriteDeleteAPIView.as_view(),
        name="favorites-delete",
    ),
    path("<int:pk>/", EventRetrieveAPIView.as_view(), name="event-detail"),
    # Admin event management
    path(
        "admin/events/", AdminEventListCreateAPIView.as_view(), name="admin-event-list"
    ),
    path(
        "admin/events/<int:pk>/",
        AdminEventRetrieveUpdateDestroyAPIView.as_view(),
        name="admin-event-detail",
    ),
    path("admin/stats/", AdminDashboardStatsAPIView.as_view(), name="admin-stats"),
]
