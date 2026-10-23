from django.urls import path

from .views import (
    events_list_page,
    event_detail_page,
    EventListAPIView,
    FilteredEventsAPIView,
    EventRetrieveAPIView,
    AdminEventListCreateAPIView,
    AdminEventRetrieveUpdateDestroyAPIView,
    AdminDashboardStatsAPIView,
)

urlpatterns = [
    # HTML pages
    path("page/", events_list_page, name="events-page"),
    path("page/<int:event_id>/", event_detail_page, name="event-details-page"),
    path("admin/stats/", AdminDashboardStatsAPIView.as_view(), name="admin-stats"),
    path(
        "admin/events/",
        AdminEventListCreateAPIView.as_view(),
        name="admin-event-list-create",
    ),
    path(
        "admin/events/<int:pk>/",
        AdminEventRetrieveUpdateDestroyAPIView.as_view(),
        name="admin-event-detail",
    ),
    # APIs
    path("", EventListAPIView.as_view(), name="events-api"),
    path("filtered/", FilteredEventsAPIView.as_view(), name="events-filtered-api"),
    path("<int:pk>/", EventRetrieveAPIView.as_view(), name="event-detail-api"),
]
