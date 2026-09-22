from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from unfold.contrib.filters.admin import AutocompleteSelectFilter, RelatedDropdownFilter
from unfold.decorators import display

from haxball_site.admin import UnfoldModelAdmin, UnfoldTabularInline
from tournament.models import Match

from .models import (
    HandicapOutcome,
    MatchPredictionOffer,
    MatchPredictionOutcome,
    Prediction,
    PredictionsContestTournament,
    PredictionSubmission,
    PreseasonPredictionItem,
    PreseasonPredictionsTournament,
    PreseasonPredictionSubmission,
    ResultOutcome,
    TotalOutcome,
)


class PredictionInline(UnfoldTabularInline):
    model = Prediction
    extra = 0
    readonly_fields = ['match']
    fields = ['match', 'predicted_result', 'outcome', 'is_special']


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


STANDARD_RESULT_SELECTIONS = ['HW', 'HWD', 'D', 'AWD', 'AW']


def outcome_form_for(fixed_market, selection_choices):
    """Build a ModelForm fixing market and limiting selection choices."""

    class OutcomeInlineForm(forms.ModelForm):
        class Meta:
            model = MatchPredictionOutcome
            fields = ('market', 'selection', 'line', 'coefficient')

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['market'].initial = fixed_market
            self.fields['market'].disabled = True
            self.fields['selection'].choices = selection_choices

    return OutcomeInlineForm


class StandardResultsFormSet(BaseInlineFormSet):
    """Prefill the 5 standard RESULT rows on the Offer add page.

    Only the selection is preset; coefficient stays empty. The same initial
    is attached on submit so untouched rows compare as unchanged and are
    skipped by the formset — only rows with a filled coefficient are
    created. Nothing is auto-created on save.
    """

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        if instance is not None and instance.pk is None:
            kwargs = {
                **kwargs,
                'initial': [
                    {
                        'market': MatchPredictionOutcome.Market.RESULT,
                        'selection': code,
                        'coefficient': '',
                    }
                    for code in STANDARD_RESULT_SELECTIONS
                ],
            }
        super().__init__(*args, **kwargs)


class BaseOutcomeInline(UnfoldTabularInline):
    fk_name = 'offer'
    extra = 0


class ResultsInline(BaseOutcomeInline):
    model = ResultOutcome
    formset = StandardResultsFormSet
    form = outcome_form_for(
        MatchPredictionOutcome.Market.RESULT,
        [('HW', 'П1'), ('HWD', '1X'), ('D', 'X'), ('AWD', 'X2'), ('AW', 'П2')],
    )
    fields = ('market', 'selection', 'coefficient')
    verbose_name = 'Основной исход'
    verbose_name_plural = 'Основные исходы'

    def get_extra(self, request, obj=None, **kwargs):
        # 5 preset rows on the add page; nothing extra when editing.
        return 5 if obj is None else 0


class HandicapsInline(BaseOutcomeInline):
    model = HandicapOutcome
    form = outcome_form_for(
        MatchPredictionOutcome.Market.HANDICAP,
        [('F1', 'Ф1'), ('F2', 'Ф2')],
    )
    fields = ('market', 'selection', 'line', 'coefficient')
    verbose_name = 'Фора'
    verbose_name_plural = 'Форы'


class TotalsInline(BaseOutcomeInline):
    model = TotalOutcome
    form = outcome_form_for(
        MatchPredictionOutcome.Market.TOTAL,
        [('OVER', 'ТБ'), ('UNDER', 'ТМ')],
    )
    fields = ('market', 'selection', 'line', 'coefficient')
    verbose_name = 'Тотал'
    verbose_name_plural = 'Тоталы'


@admin.register(MatchPredictionOffer)
class MatchPredictionOfferAdmin(UnfoldModelAdmin):
    list_display = ['match', 'is_published', 'display_results', 'display_handicaps', 'display_totals']
    list_filter = [
        ('match__league', RelatedDropdownFilter),
        ('match__numb_tour', RelatedDropdownFilter),
        'is_published',
    ]
    list_filter_sheet = False
    list_filter_submit = True
    search_fields = ['match__team_home__title', 'match__team_guest__title']
    ordering = ['-id']
    inlines = [ResultsInline, HandicapsInline, TotalsInline]

    @display(description='Исходы', dropdown=True)
    def display_results(self, model):
        return self._market_dropdown(model, MatchPredictionOutcome.Market.RESULT)

    @display(description='Форы', dropdown=True)
    def display_handicaps(self, model):
        return self._market_dropdown(model, MatchPredictionOutcome.Market.HANDICAP)

    @display(description='Тоталы', dropdown=True)
    def display_totals(self, model):
        return self._market_dropdown(model, MatchPredictionOutcome.Market.TOTAL)

    @staticmethod
    def _market_dropdown(model, market):
        outcomes = [o for o in model.outcomes.all() if o.market == market]
        return {
            'title': len(outcomes),
            'items': [{'title': f'{o.display_label} ×{o.coefficient}'} for o in outcomes],
        }

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('outcomes')

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
