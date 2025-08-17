from django.urls import path

from . import views

app_name = 'predictions'

urlpatterns = [
    path('', views.predictions_main, name='main'),
    path('make-predictions/', views.make_predictions_tab, name='make_predictions_tab'),
    path('view-predictions/', views.view_predictions_tab, name='view_predictions_tab'),
    path('standings/', views.standings_tab, name='standings_tab'),
    path('edit/<int:tour_id>/', views.edit_predictions, name='edit_predictions'),
    path('tour-card/<int:tour_id>/', views.tour_card, name='tour_card'),
    # Long-term predictions
    path('longterm/', views.longterm, name='longterm'),
    path('longterm/my/', views.longterm_my_tab, name='longterm_my_tab'),
    path('longterm/results/', views.longterm_results_tab, name='longterm_results_tab'),
    path('longterm/save/', views.longterm_save, name='longterm_save'),
]
