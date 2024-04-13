from django.urls import path

from .views import FreeAgentList, remove_entry, update_entry, TeamDetail, TeamList, LeagueDetail, MatchDetail, \
    edit_team_profile, halloffame, team_rating, DisqualificationsList, PostponementsList, cancel_postponement, \
    TransfersList

app_name = 'tournament'

urlpatterns = [
    # Зал славы
    path('hall_of_fame', halloffame, name='hall_of_fame'),
    path('postponements', PostponementsList.as_view(), name='postponements'),
    path('postponements/<int:pk>/cancel', cancel_postponement, name='cancel_postponement'),
    path('team_rating', team_rating, name='team_rating'),
    path('free_agents/', FreeAgentList.as_view(), name='free_agent'),
    path('free_agents/remove/<int:pk>', remove_entry, name='remove_entry'),
    path('free_agents/update/<int:pk>', update_entry, name='update_entry'),
    path('team/<slug:slug>', TeamDetail.as_view(), name='team_detail'),
    path('team/<slug:slug>/edit', edit_team_profile, name='edit_team'),
    path('teams/', TeamList.as_view(), name='team_list'),
    path('disqualifications', DisqualificationsList.as_view(), name='disqualifications'),
    path('transfers', TransfersList.as_view(), name='transfers'),
    path('<slug:slug>', LeagueDetail.as_view(), name='league'),
    path('match/<int:pk>', MatchDetail.as_view(), name='match_detail'),
]
