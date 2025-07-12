from django.contrib import admin

from unfold.admin import ModelAdmin, TabularInline

from .models import Prediction, PredictionSubmission, PredictionTournament


class PredictionInline(TabularInline):
    model = Prediction
    extra = 0
    readonly_fields = ['match']
    fields = ['match', 'predicted_result']


@admin.register(PredictionTournament)
class PredictionTournamentAdmin(ModelAdmin):
    list_display = ['league', 'is_active']
    list_filter = ['is_active']
    search_fields = ['league__title']
    ordering = ['-id']


@admin.register(PredictionSubmission)
class PredictionSubmissionAdmin(ModelAdmin):
    list_filter = ['tournament', 'tour__league', 'created']
    search_fields = ['user__username', 'tour__number']
    ordering = ['-created']
    inlines = [PredictionInline]
    readonly_fields = ['user', 'tournament', 'tour', 'created', 'updated']


@admin.register(Prediction)
class PredictionAdmin(ModelAdmin):
    list_display = ['submission', 'match', 'predicted_result']
    list_filter = ['predicted_result', 'match__league']
    search_fields = ['submission__user__username', 'match__team_home__title', 'match__team_guest__title']
    ordering = ['-submission__created']
