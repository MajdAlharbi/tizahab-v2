from django.urls import path
from .views import events_list_page, event_detail_page

urlpatterns = [
    path("page/", events_list_page, name="events-page"),
    path("page/<int:event_id>/", event_detail_page, name="event-detail-page"),
]
