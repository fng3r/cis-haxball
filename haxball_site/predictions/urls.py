from django.urls import path

from . import views

app_name = 'predictions'

urlpatterns = [
    path('', views.predictions_main, name='main'),
    path('contest/', views.predictions_contest_tab, name='predictions_contest'),
    path('make-predictions/', views.make_predictions_tab, name='make_predictions_tab'),
    path('view-predictions/', views.view_predictions_tab, name='view_predictions_tab'),
    path('standings/', views.standings_tab, name='standings_tab'),
    path('rewards/', views.rewards_tab, name='rewards_tab'),
    path('edit/<int:tour_id>/', views.edit_predictions, name='edit_predictions'),
    path('tour-card/<int:tour_id>/', views.tour_card, name='tour_card'),
    # Preseason predictions
    path('preseason/', views.preseason, name='preseason'),
    path('preseason/my/', views.preseason_my_tab, name='preseason_my_tab'),
    path('preseason/results/', views.preseason_results_tab, name='preseason_results_tab'),
    path('preseason/ranking/', views.preseason_ranking_tab, name='preseason_ranking_tab'),
    path('preseason/save/', views.preseason_save, name='preseason_save'),
]
