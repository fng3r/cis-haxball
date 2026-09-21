from django.contrib import admin

from unfold.admin import display
from unfold.contrib.filters.admin import AutocompleteSelectFilter, RelatedDropdownFilter

from haxball_site.admin import UnfoldModelAdmin, UnfoldTabularInline
from tournament.models import Match

from .models import (
    MatchPredictionCoefficients,
    Prediction,
    PredictionsContestTournament,
    PredictionSubmission,
    PreseasonPredictionItem,
    PreseasonPredictionsTournament,
    PreseasonPredictionSubmission,
)


class PredictionInline(UnfoldTabularInline):
    model = Prediction
    extra = 0
    readonly_fields = ['match']
    fields = ['match', 'predicted_result', 'is_special']


@admin.register(PredictionsContestTournament)
class PredictionsContestTournamentAdmin(UnfoldModelAdmin):
    list_display = [
        'league',
        'is_active',
        'scoring_method',
        'nominal_points',
        'points_for_win_prediction',
        'points_for_draw_prediction',
        'special_match_points_delta',
    ]
    list_editable = [
        'is_active',
        'scoring_method',
        'nominal_points',
        'points_for_win_prediction',
        'points_for_draw_prediction',
        'special_match_points_delta',
    ]
    list_filter = ['is_active']
    list_filter_sheet = False
    search_fields = ['league__title']
    ordering = ['-id']


@admin.register(MatchPredictionCoefficients)
class MatchPredictionCoefficientsAdmin(UnfoldModelAdmin):
    list_display = [
        'match',
        'home_win',
        'home_win_or_draw',
        'draw',
        'away_win_or_draw',
        'away_win',
    ]
    list_filter = [
        ('match__league', RelatedDropdownFilter),
        ('match__numb_tour', RelatedDropdownFilter),
    ]
    list_filter_sheet = False
    list_filter_submit = True
    search_fields = ['match__team_home__title', 'match__team_guest__title']
    ordering = ['-id']

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'match',
                    ('home_win', 'home_win_or_draw'),
                    ('draw',),
                    ('away_win_or_draw', 'away_win'),
                )
            },
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'match':
            coefficient_tournament_leagues = PredictionsContestTournament.objects.filter(
                scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENT
            ).values_list('league_id', flat=True)
            kwargs['queryset'] = Match.objects.filter(league_id__in=coefficient_tournament_leagues)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PredictionSubmission)
class PredictionSubmissionAdmin(UnfoldModelAdmin):
    list_display = ['tournament', 'tour', 'user', 'created', 'updated']
    list_filter = [('user', AutocompleteSelectFilter), ('tournament__league', RelatedDropdownFilter), 'created']
    list_filter_submit = True
    search_fields = ['user__username', 'tour__number']
    ordering = ['-created']
    inlines = [PredictionInline]
    readonly_fields = ['user', 'tournament', 'tour', 'created', 'updated']


@admin.register(PreseasonPredictionsTournament)
class PreseasonPredictionsTournamentAdmin(UnfoldModelAdmin):
    list_display = ['league', 'locked_at', 'display_is_active']
    list_filter = ['locked_at']
    list_filter_sheet = False
    search_fields = ['league__title']
    ordering = ['-id']

    @display(description='Сбор прогнозов открыт', boolean=True)
    def display_is_active(self, model):
        return model.is_active


class PreseasonPredictionItemInline(UnfoldTabularInline):
    model = PreseasonPredictionItem
    extra = 0
    readonly_fields = ['team', 'position']
    fields = ['team', 'position']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PreseasonPredictionSubmission)
class PreseasonPredictionSubmissionAdmin(UnfoldModelAdmin):
    list_display = ['tournament', 'user', 'created', 'updated']
    list_filter = [('user', AutocompleteSelectFilter), ('tournament__league', RelatedDropdownFilter)]
    list_filter_submit = True
    search_fields = ['user__username', 'tournament__league__title']
    inlines = [PreseasonPredictionItemInline]
    readonly_fields = ['user', 'tournament', 'created', 'updated']
