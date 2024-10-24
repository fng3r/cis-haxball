from django.urls import path

from .views import (
    DisqualificationsList,
    EditTeamView,
    FreeAgentList,
    LeagueDetail,
    MatchDetail,
    PostponementsEvents,
    PostponementsList,
    TeamDetail,
    TeamList,
    TeamRatingView,
    TransfersList,
    cancel_postponement,
    halloffame,
    player_detailed_statistics,
    player_statistics_charts,
    remove_entry,
    team_statistics,
    team_statistics_charts,
    update_entry, CardsList,
)

app_name = 'tournament'

urlpatterns = [
    # Зал славы
    path('hall_of_fame', halloffame, name='hall_of_fame'),
    path('postponements', PostponementsList.as_view(), name='postponements'),
    path('postponements/events', PostponementsEvents.as_view(), name='postponements_events'),
    path('postponements/<int:pk>/cancel', cancel_postponement, name='cancel_postponement'),
    path('team_rating', TeamRatingView.as_view(), name='team_rating'),
    path('free_agents/', FreeAgentList.as_view(), name='free_agents'),
    path('free_agents/remove/<int:pk>', remove_entry, name='remove_entry'),
    path('free_agents/update/<int:pk>', update_entry, name='update_entry'),
    path('team/<slug:slug>', TeamDetail.as_view(), name='team_detail'),
    path('team/<slug:slug>/edit', EditTeamView.as_view(), name='edit_team'),
    path('teams/', TeamList.as_view(), name='team_list'),
    path('disqualifications', DisqualificationsList.as_view(), name='disqualifications'),
    path('cards', CardsList.as_view(), name='cards'),
    path('transfers', TransfersList.as_view(), name='transfers'),
    path('<slug:slug>', LeagueDetail.as_view(), name='league'),
    path('match/<int:pk>', MatchDetail.as_view(), name='match_detail'),
    path('player_stats/<int:pk>', player_detailed_statistics, name='player_stats'),
    path('player_stats/<int:pk>/charts', player_statistics_charts, name='player_stats_charts'),
    path('team_stats/<int:pk>', team_statistics, name='team_stats'),
    path('team_stats/<int:pk>/charts', team_statistics_charts, name='team_stats_charts'),
]
