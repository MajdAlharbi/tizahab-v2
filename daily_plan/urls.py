from django.urls import path
from .views import (
    DailyPlanAddAPIView,
    DailyPlanListCreateAPIView,
    DailyPlanRetrieveUpdateDestroyAPIView,
    DailyPlanEventRemoveAPIView,
    DailyPlanItemDetailAPIView,
    DailyPlanItemListCreateAPIView,
    GenerateDailyPlanAPIView,
    GenerateMultiDayPlanAPIView,
)

app_name = "daily_plan"

urlpatterns = [
    path("", DailyPlanListCreateAPIView.as_view(), name="daily-plan"),
    path("add/", DailyPlanAddAPIView.as_view(), name="daily-plan-add"),
    path("generate/", GenerateDailyPlanAPIView.as_view(), name="daily-plan-generate"),
    path(
        "generate-multiday/",
        GenerateMultiDayPlanAPIView.as_view(),
        name="daily-plan-generate-multiday",
    ),
    path(
        "<int:pk>/",
        DailyPlanRetrieveUpdateDestroyAPIView.as_view(),
        name="daily-plan-detail",
    ),
    path(
        "<int:pk>/events/<int:event_id>/",
        DailyPlanEventRemoveAPIView.as_view(),
        name="daily-plan-event-remove",
    ),
    path(
        "<int:pk>/items/",
        DailyPlanItemListCreateAPIView.as_view(),
        name="daily-plan-item-list-create",
    ),
    path(
        "<int:pk>/items/<int:item_id>/",
        DailyPlanItemDetailAPIView.as_view(),
        name="daily-plan-item-detail",
    ),
]
