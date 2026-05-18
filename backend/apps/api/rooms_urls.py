from django.urls import path

from apps.api.rooms_views import UnitCalendarView, UnitListView

urlpatterns = [
    path("rooms/", UnitListView.as_view(), name="rooms-list"),
    path(
        "rooms/<int:room_id>/calendar/",
        UnitCalendarView.as_view(),
        name="rooms-calendar",
    ),
]
