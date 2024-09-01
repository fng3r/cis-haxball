from django.urls import path

from .views import ReplaysList, ReservationList, delete_entry

app_name = 'reservation'

urlpatterns = [
    path('', ReservationList.as_view(), name='host_reservation'),
    path('remove/<int:pk>', delete_entry, name='delete_entry'),
    path('replays/', ReplaysList.as_view(), name='replays_list'),
]
