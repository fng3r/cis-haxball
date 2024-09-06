from django.urls import path

from .views import ReplaysList, ReservationList, delete_entry, get_reservation_form

app_name = 'reservation'

urlpatterns = [
    path('', ReservationList.as_view(), name='host_reservation'),
    path('form', get_reservation_form, name='host_reservation_form'),
    path('remove/<int:pk>', delete_entry, name='delete_entry'),
    path('replays/', ReplaysList.as_view(), name='replays_list'),
]
