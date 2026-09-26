"""Admin betting-style dashboard for the predictions app.

Displays matches with all available outcomes and coefficients in a
bookmaker-line layout, using django-unfold building blocks:

- ``UnfoldModelAdminViewMixin`` custom admin view (``custom_urls``)
- ``@display`` with ``label`` / ``boolean`` / ``dropdown`` / ``header``
- ``TableSection`` / ``TemplateSection`` per-row previews (``list_sections``)
- ``@action`` shortcuts with icons (``actions_list`` / ``actions_row``)
- ``DASHBOARD_CALLBACK`` KPIs + ``TABS`` / ``SIDEBAR`` navigation
"""

from collections import defaultdict
from decimal import Decimal

from django import forms
from django.db.models import Avg, Count, Q
from django.views.generic import TemplateView

from unfold.sections import TemplateSection
from unfold.views import UnfoldModelAdminViewMixin
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from tournament.models import Match, PlayOffStage, TourNumber

from .models import MatchPredictionOffer, MatchPredictionOutcome, Prediction, PredictionsContestTournament
from .points_service import calculate_prediction_points, is_prediction_correct, is_prediction_void

MARKET_LABELS = {
    MatchPredictionOutcome.Market.RESULT: 'Исход матча',
    MatchPredictionOutcome.Market.HANDICAP: 'Фора',
    MatchPredictionOutcome.Market.TOTAL: 'Тотал',
    MatchPredictionOutcome.Market.INDIVIDUAL_TOTAL: 'Инд. тотал',
}

MARKET_ICONS = {
    MatchPredictionOutcome.Market.RESULT: 'sports_soccer',
    MatchPredictionOutcome.Market.HANDICAP: 'balance',
    MatchPredictionOutcome.Market.TOTAL: 'functions',
    MatchPredictionOutcome.Market.INDIVIDUAL_TOTAL: 'person',
}

MARKET_ORDER = MatchPredictionOutcome.MARKET_ORDER


def outcome_tone(outcome) -> str:
    """Map a coefficient to an unfold label tone for the betting board."""
    coefficient = Decimal(outcome.coefficient)
    if coefficient < Decimal('1.70'):
        return 'success'
    if coefficient < Decimal('2.50'):
        return 'info'
    if coefficient < Decimal('4.00'):
        return 'warning'
    return 'danger'


def group_outcomes_by_market(outcomes):
    """Group outcomes preserving canonical market order."""
    grouped = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.market].append(outcome)
    return {market: grouped[market] for market in MARKET_ORDER if market in grouped}


class BettingBoardFilterForm(forms.Form):
    """Filters rendered with unfold widgets on the betting board."""

    tournament = forms.ModelChoiceField(
        queryset=PredictionsContestTournament.objects.filter(
            scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS
        ).select_related('league__championship'),
        required=False,
        empty_label='Все турниры (коэффициенты)',
        widget=UnfoldAdminSelectWidget,
    )
    tour = forms.ModelChoiceField(
        queryset=TourNumber.objects.none(),
        required=False,
        empty_label='Все туры',
        widget=UnfoldAdminSelectWidget,
    )
    q = forms.CharField(required=False, widget=UnfoldAdminTextInputWidget(attrs={'placeholder': 'Команда…'}))
    hide_played = forms.BooleanField(required=False)
    only_published = forms.BooleanField(required=False, initial=True)
    only_with_line = forms.BooleanField(required=False, initial=False)


def get_board_queryset(*, tournament=None, tour=None, q='', hide_played=False, only_published=True):
    """Base match queryset for the board with all relations prefetched."""
    filters = Q()
    if tournament is not None:
        filters &= Q(league_id=tournament.league_id)
    else:
        coefficient_league_ids = PredictionsContestTournament.objects.filter(
            scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS
        ).values_list('league_id', flat=True)
        filters &= Q(league_id__in=coefficient_league_ids)
    if tour is not None:
        filters &= Q(numb_tour_id=tour.pk)
    if hide_played:
        filters &= Q(is_played=False)
    if q:
        filters &= Q(team_home__title__icontains=q) | Q(team_guest__title__icontains=q)

    return (
        Match.objects.filter(filters)
        .select_related('team_home', 'team_guest', 'result', 'numb_tour__league', 'league__championship')
        .prefetch_related(
            'prediction_offer__outcomes',
            'predictions__outcome',
            'predictions__submission__user',
            'predictions__submission__user__user_profile',
            'predictions__submission__tournament',
        )
        .order_by('numb_tour__number', 'id')
    )


def build_pick_details(match):
    """Build per-prediction rows for the match spoiler: user, outcome, settlement, P/L."""
    details = []
    for prediction in match.predictions.all():
        submission = getattr(prediction, 'submission', None)
        user = getattr(submission, 'user', None)
        outcome = getattr(prediction, 'outcome', None)
        played = match.is_played
        void = is_prediction_void(prediction) if played else False
        correct = is_prediction_correct(prediction) if played and not void else False
        avatar_url = None
        profile = getattr(user, 'user_profile', None)
        if profile is not None:
            try:
                avatar_url = profile.avatar.url
            except (AttributeError, ValueError):
                avatar_url = None
        details.append(
            {
                'user_id': user.pk if user is not None else None,
                'username': user.username if user is not None else '—',
                'avatar_url': avatar_url,
                'outcome_label': prediction.outcome_label,
                'coefficient': outcome.coefficient if outcome is not None else None,
                'played': played,
                'is_void': void,
                'is_correct': correct,
                'points': calculate_prediction_points(prediction) if played else None,
            }
        )
    details.sort(key=lambda row: (row['outcome_label'].lower(), row['username'].lower()))
    return details


def build_match_cards(matches, *, only_published=True, only_with_line=False):
    """Build betting-style cards: match + grouped outcomes + pick counters."""
    cards = []
    for match in matches:
        offer = getattr(match, 'prediction_offer', None)
        if offer is None:
            if only_with_line:
                continue
            pick_details = build_pick_details(match)
            cards.append(
                {
                    'match': match,
                    'offer': None,
                    'groups': {},
                    'outcomes': [],
                    'total_outcomes': 0,
                    'total_picks': len(pick_details),
                    'picks_by_outcome': {},
                    'pick_details': pick_details,
                    'is_published': False,
                    'has_line': False,
                }
            )
            continue
        if only_published and not offer.is_published:
            continue
        outcomes = sorted(
            list(offer.outcomes.all()),
            key=lambda o: (
                MARKET_ORDER.index(o.market) if o.market in MARKET_ORDER else 99,
                o.id or 0,
            ),
        )
        if only_with_line and not outcomes:
            continue
        picks_by_outcome = defaultdict(int)
        for prediction in match.predictions.all():
            if prediction.outcome_id:
                picks_by_outcome[prediction.outcome_id] += 1
        pick_details = build_pick_details(match)
        cards.append(
            {
                'match': match,
                'offer': offer,
                'groups': group_outcomes_by_market(outcomes),
                'outcomes': outcomes,
                'total_outcomes': len(outcomes),
                'total_picks': len(pick_details),
                'picks_by_outcome': dict(picks_by_outcome),
                'pick_details': pick_details,
                'is_published': offer.is_published,
                'has_line': bool(outcomes),
            }
        )
    return cards


def build_board_stats(cards):
    """Aggregate KPIs for the board header."""
    coefficients = [Decimal(o.coefficient) for card in cards for o in card['outcomes']]
    return {
        'matches': len(cards),
        'with_line': sum(1 for card in cards if card['has_line']),
        'without_line': sum(1 for card in cards if not card['has_line']),
        'published': sum(1 for card in cards if card['is_published']),
        'outcomes': sum(card['total_outcomes'] for card in cards),
        'picks': sum(card['total_picks'] for card in cards),
        'avg_coefficient': (sum(coefficients) / len(coefficients)) if coefficients else None,
        'min_coefficient': min(coefficients) if coefficients else None,
        'max_coefficient': max(coefficients) if coefficients else None,
    }


def build_market_stats(cards):
    """Per-market distribution for progress bars and charts."""
    per_market = defaultdict(list)
    for card in cards:
        for outcome in card['outcomes']:
            per_market[outcome.market].append(Decimal(outcome.coefficient))
    total = sum(len(values) for values in per_market.values()) or 1
    stats = []
    for market in MARKET_ORDER:
        values = per_market.get(market, [])
        stats.append(
            {
                'market': market,
                'label': MARKET_LABELS.get(market, market),
                'icon': MARKET_ICONS.get(market, 'tag'),
                'count': len(values),
                'share': round(len(values) / total * 100) if values else 0,
                'avg': (sum(values) / len(values)) if values else None,
            }
        )
    return stats


class PredictionsBettingBoardView(UnfoldModelAdminViewMixin, TemplateView):
    """Bookmaker-line dashboard: matches with outcomes and coefficients."""

    title = 'Букмекерская линия прогнозов'
    template_name = 'admin/predictions/betting_board.html'
    permission_required = ('predictions.view_matchpredictionoffer',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        tournaments = (
            PredictionsContestTournament.objects.filter(
                scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS
            )
            .select_related('league__championship')
            .order_by('league__priority')
        )
        tournament = None
        tournament_id = self.request.GET.get('tournament')
        if tournament_id:
            tournament = tournaments.filter(pk=tournament_id).first()
        if tournament is None:
            tournament = tournaments.first()

        tours = TourNumber.objects.none()
        if tournament is not None:
            playoff_stage_ids = PlayOffStage.objects.filter(league=tournament.league).values_list('pk', flat=True)
            tours = (
                TourNumber.objects.filter(league=tournament.league)
                .exclude(stage_id__in=playoff_stage_ids)
                .order_by('number')
            )
        tour = None
        tour_id = self.request.GET.get('tour')
        if tour_id:
            tour = tours.filter(pk=tour_id).first()

        form = BettingBoardFilterForm(self.request.GET or None)
        form.fields['tournament'].queryset = tournaments
        form.fields['tour'].queryset = tours
        if not form.is_bound:
            form.initial.update(
                {
                    'tournament': tournament.pk if tournament else None,
                    'only_published': True,
                }
            )

        q = self.request.GET.get('q', '').strip()
        hide_played = self.request.GET.get('hide_played') == 'on'
        # Unchecked checkboxes are absent from GET, so defaulting to 'on'
        # would re-enable the flag on every submit. Default to True only
        # on the initial (unfiltered) load.
        only_published = self.request.GET.get('only_published') == 'on' if form.is_bound else True
        only_with_line = self.request.GET.get('only_with_line') == 'on'

        matches = get_board_queryset(
            tournament=tournament,
            tour=tour,
            q=q,
            hide_played=hide_played,
            only_published=False,
        )
        cards = build_match_cards(matches, only_published=only_published, only_with_line=only_with_line)

        # Group cards by tour for the betting-style sections.
        cards_by_tour = defaultdict(list)
        for card in cards:
            cards_by_tour[card['match'].numb_tour_id].append(card)
        tours_map = {t.id: t for t in tours}
        sections = []
        for tour_id_key, tour_cards in sorted(cards_by_tour.items()):
            tour_obj = tours_map.get(tour_id_key)
            if tour_obj is not None:
                title = f'{tour_obj.number} тур · {tour_obj.date_from:%d.%m}–{tour_obj.date_to:%d.%m}'
            else:
                title = 'Без тура'
            bettors = {
                pick['user_id'] for card in tour_cards for pick in card['pick_details'] if pick['user_id'] is not None
            }
            stats = build_board_stats(tour_cards)
            stats['bettors'] = len(bettors)
            sections.append(
                {
                    'tour': tour_obj,
                    'tour_id': tour_id_key,
                    'title': title,
                    'cards': tour_cards,
                    'stats': stats,
                }
            )

        context.update(
            {
                'tournaments': tournaments,
                'selected_tournament': tournament,
                'tours': tours,
                'selected_tour': tour,
                'filter_form': form,
                'query': q,
                'hide_played': hide_played,
                'only_published': only_published,
                'only_with_line': only_with_line,
                'sections': sections,
                'stats': build_board_stats(cards),
                'market_stats': build_market_stats(cards),
                'market_labels': MARKET_LABELS,
                'market_icons': MARKET_ICONS,
            }
        )
        return context


class OfferBettingPreviewSection(TemplateSection):
    """Per-row betting preview on the offer changelist (``list_sections``)."""

    template_name = 'admin/predictions/_offer_line_preview.html'

    def get_context_data(self, request, instance):
        offer = instance
        outcomes = sorted(
            list(offer.outcomes.all()),
            key=lambda o: (
                MARKET_ORDER.index(o.market) if o.market in MARKET_ORDER else 99,
                o.id or 0,
            ),
        )
        return {
            'offer': offer,
            'match': offer.match,
            'groups': group_outcomes_by_market(outcomes),
            'market_labels': MARKET_LABELS,
            'market_icons': MARKET_ICONS,
        }


def predictions_dashboard_callback(request, context):
    """``DASHBOARD_CALLBACK``: predictions KPIs for the main admin index."""
    offers = MatchPredictionOffer.objects.select_related('match').prefetch_related('outcomes')
    outcomes_qs = MatchPredictionOutcome.objects.all()
    coefficient_tournaments = PredictionsContestTournament.objects.filter(
        scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS
    ).select_related('league')

    aggregate = outcomes_qs.aggregate(
        total=Count('id'),
        avg=Avg('coefficient'),
    )
    per_market = list(outcomes_qs.values('market').annotate(total=Count('id'), avg=Avg('coefficient')))
    total_picks = Prediction.objects.filter(outcome__isnull=False).count()

    context.update(
        {
            'predictions_kpis': {
                'tournaments': coefficient_tournaments.count(),
                'offers': offers.count(),
                'published': offers.filter(is_published=True).count(),
                'outcomes': aggregate['total'] or 0,
                'avg_coefficient': aggregate['avg'],
                'picks': total_picks,
            },
            'predictions_per_market': per_market,
            'predictions_market_labels': MARKET_LABELS,
        }
    )
    return context
