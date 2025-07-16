from django.urls import path

from . import views

app_name = 'fantasy_league'

urlpatterns = [
    path('', views.fantasy_main, name='main'),
    path('make-squad/', views.make_squad_tab, name='make_squad_tab'),
    path('view-squads/', views.view_squads_tab, name='view_squads_tab'),
    path('standings/', views.standings_tab, name='standings_tab'),
    path('statistics/', views.statistics_tab, name='statistics_tab'),
    path('tour/<int:tour_id>/edit/', views.edit_squad, name='edit_squad'),
    path('tour/<int:tour_id>/', views.tour_detail, name='tour_detail'),
]
