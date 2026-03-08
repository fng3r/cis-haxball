from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from django_htmx.http import trigger_client_event

from fantasy_league.forms import TourFilterForm
from tournament.models import Season, TourNumber

from .forms import (
    PreseasonPredictionsTournamentFilterForm,
    SeasonFilterForm,
    TournamentFilterForm,
    UserFilterForm,
)
from .models import (
    Prediction,
    PredictionsContestTournament,
    PredictionSubmission,
    PreseasonPredictionItem,
    PreseasonPredictionsTournament,
    PreseasonPredictionSubmission,
)
from .points_service import (
    calculate_preseason_submission_points,
    calculate_submission_total_points,
    get_teams_actual_positions,
)
from .utils import (
    calculate_tour_rewards,
    get_tournament_standings,
    is_tour_open_for_predictions,
)


def resolve_selected_season(request):
    """Return (selected_season, season_form) for predictions contests."""
    seasons = (
        Season.objects.filter(tournaments_in_season__predictions_contest_tournament__isnull=False)
        .distinct()
        .order_by('-number')
    )

    selected_season = None
    season_id = request.GET.get('season')
    if season_id:
        selected_season = seasons.filter(pk=season_id).first()
    if selected_season is None and seasons.exists():
        selected_season = seasons.filter(is_active=True).first() or seasons.first()

    season_form = SeasonFilterForm(
        seasons,
        initial={'season': selected_season.pk if selected_season else None},
    )

    return selected_season, season_form


def get_default_tournament(season: Season | None = None):
    """Return default predictions tournament, optionally scoped to a season (prefer active)."""
    queryset = PredictionsContestTournament.objects.select_related('league__championship')
    if season is not None:
        queryset = queryset.filter(league__championship=season)

    return queryset.order_by('league__priority').first()


def get_default_preseason_tournament(season: Season | None = None):
    """Return default preseason predictions tournament, optionally scoped to a season (prefer active)."""
    queryset = PreseasonPredictionsTournament.objects.select_related('league__championship')
    if season is not None:
        queryset = queryset.filter(league__championship=season)

    return queryset.order_by('league__priority').first()


def resolve_selected_tournament(request, selected_tournament=None, season: Season | None = None):
    """Resolve selected tournament from GET or provided value.

    Ensures the tournament is enriched with league and prefetches tours for later use.
    """
    default_tournament = get_default_tournament(season=season)

    # If explicit tournament object provided, just re-fetch it with prefetches.
    if selected_tournament is None:
        if request.GET.get('tournament'):
            selected_tournament = PredictionsContestTournament.objects.filter(pk=request.GET.get('tournament')).first()
        elif default_tournament:
            selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            PredictionsContestTournament.objects.filter(pk=selected_tournament.pk)
            .select_related('league')
            .prefetch_related(
                'league__tours',
                'league__tours__tour_matches__team_home',
                'league__tours__tour_matches__team_guest',
                'league__tours__tour_matches__result',
            )
            .first()
        )

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None},
        season=season,
    )

    return selected_tournament, tournament_form


def resolve_selected_tour(request, selected_tournament):
    """Resolve selected tour from GET or provided value and return (tour, TourFilterForm)."""

    tour = None
    tour_form = None
    if selected_tournament:
        tour_qs = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')
        initial_tour = None
        if request.GET.get('tour'):
            initial_tour = tour_qs.filter(pk=request.GET.get('tour')).first()
        if not initial_tour:
            latest_submitted_tour = (
                PredictionSubmission.objects.filter(
                    tournament=selected_tournament, tour__date_to__lt=timezone.localdate()
                )
                .order_by('-tour__number')
                .values(number=F('tour__number'))
                .first()
            )
            if latest_submitted_tour:
                initial_tour = tour_qs.filter(number=latest_submitted_tour['number']).first()
        tour = initial_tour
        tour_form = TourFilterForm(
            initial={'tour': initial_tour.pk if initial_tour else None},
            league=selected_tournament.league,
        )

    return tour, tour_form


def resolve_selected_preseason_tournament(request, selected_tournament=None, season: Season | None = None):
    """Resolve selected preseason tournament from GET or provided value.

    Ensures the tournament is enriched with league and prefetches teams for later use.
    """
    default_tournament = get_default_preseason_tournament(season)
    if not selected_tournament:
        if request.GET.get('tournament'):
            selected_tournament = PreseasonPredictionsTournament.objects.filter(
                pk=request.GET.get('tournament')
            ).first()
        elif default_tournament:
            selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            PreseasonPredictionsTournament.objects.filter(pk=selected_tournament.pk)
            .select_related('league')
            .prefetch_related(
                'league__teams',
            )
            .first()
        )

    tournament_form = PreseasonPredictionsTournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None},
        season=season,
    )

    return selected_tournament, tournament_form


def get_users_with_predictions(tournament=None):
    """Get users who have made at least one prediction"""
    if tournament:
        return (
            User.objects.filter(prediction_submissions__tournament=tournament).select_related('user_profile').distinct()
        )
    return User.objects.filter(prediction_submissions__isnull=False).select_related('user_profile').distinct()


def predictions_main(request):
    """Main predictions page with three tabs"""
    # Seasons are only used to influence the initial/default tournament selection.
    selected_season, season_form = resolve_selected_season(request)
    selected_tournament, tournament_form = resolve_selected_tournament(request, season=selected_season)
    selected_preseason_tournament, _ = resolve_selected_preseason_tournament(request, season=selected_season)
    selected_user = None

    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    active_tournaments = PredictionsContestTournament.objects.filter(is_active=True)

    make_predictions_tab_html = make_predictions_tab(
        request, initial_context=True, selected_tournament=selected_tournament
    )

    context = {
        'season_form': season_form,
        'selected_season': selected_season,
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'selected_preseason_tournament': selected_preseason_tournament,
        'active_tournaments': active_tournaments,
        'make_predictions_tab_html': make_predictions_tab_html,
    }

    return render(request, 'predictions/main.html', context)


def predictions_contest_tab(request):
    selected_tournament, tournament_form = resolve_selected_tournament(request)
    make_predictions_tab_html = make_predictions_tab(
        request, initial_context=True, selected_tournament=selected_tournament
    )

    context = {
        'selected_tournament': selected_tournament,
        'tournament_form': tournament_form,
        'make_predictions_tab_html': make_predictions_tab_html,
    }

    if request.htmx:
        return render(request, 'predictions/contest/container.html#predictions-contest-tabs', context)

    return render(request, 'predictions/contest/container.html', context)


def make_predictions_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making predictions"""
    if not request.user.is_authenticated:
        return render_to_string(
            'predictions/contest/make_predictions_tab.html',
            {'user': request.user},
            request=request,
        )

    # Keep tournament consistent with current season selection
    selected_tournament, tournament_form = resolve_selected_tournament(request, selected_tournament)

    user_predictions = {}
    is_tournament_ended = False
    if selected_tournament:
        tours = TourNumber.objects.filter(league=selected_tournament.league).prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        )

        submissions = (
            PredictionSubmission.objects.filter(user=request.user, tournament=selected_tournament)
            .select_related('tournament')
            .prefetch_related('predictions__match__result')
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission:
                match_predictions = {pred.match_id: pred for pred in submission.predictions.all()}
                user_predictions[tour.id] = {'submission': submission, 'match_predictions': match_predictions}
            else:
                user_predictions[tour.id] = {'submission': None, 'match_predictions': {}}

        is_tournament_ended = all(tour.is_ended for tour in tours)

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'is_tournament_ended': is_tournament_ended,
        'user_predictions': user_predictions,
        'user': request.user,
    }
    if initial_context:
        return render_to_string('predictions/contest/make_predictions_tab.html', context, request=request)
    return render(request, 'predictions/contest/make_predictions_tab.html', context)


def view_predictions_tab(request):
    """Tab for viewing other users' predictions"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)

    user_id = request.GET.get('user')
    users_with_predictions = get_users_with_predictions(selected_tournament)
    selected_user = None
    if user_id:
        selected_user = User.objects.filter(pk=user_id).first()
    elif users_with_predictions:
        selected_user = users_with_predictions.first()

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    if not selected_user:
        return render(
            request,
            'predictions/contest/view_predictions_tab.html',
            {
                'tournament_form': tournament_form,
                'user_form': user_form,
                'selected_tournament': selected_tournament,
                'selected_user': selected_user,
                'predictions_data': {},
            },
        )

    if users_with_predictions:
        user_form.fields['user'].queryset = users_with_predictions

    predictions_data = {}
    if selected_tournament and selected_user:
        tours = TourNumber.objects.filter(league=selected_tournament.league).prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        )

        submissions = (
            PredictionSubmission.objects.filter(user=selected_user, tournament=selected_tournament)
            .select_related('tournament')
            .prefetch_related(
                'predictions__match__result__winner',
                'predictions__match__team_home',
                'predictions__match__team_guest',
            )
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission and not is_tour_open_for_predictions(tour):
                predictions_data[tour.id] = submission
            else:
                predictions_data[tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'selected_user': selected_user,
        'predictions_data': predictions_data,
    }

    return render(request, 'predictions/contest/view_predictions_tab.html', context)


def standings_tab(request):
    """Tab for tournament standings"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)

    standings = []
    tour_points = {}

    if selected_tournament:
        standings = get_tournament_standings(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league)

        all_submissions = (
            PredictionSubmission.objects.filter(tournament=selected_tournament)
            .select_related('tournament')
            .prefetch_related('predictions__match__result')
        )

        submissions_lookup = {}
        for submission in all_submissions:
            key = (submission.user_id, submission.tour_id)
            submissions_lookup[key] = submission

        for standing in standings:
            user = standing['user']
            tour_points[user.id] = {}
            for tour in tours:
                submission = submissions_lookup.get((user.id, tour.id))
                if submission:
                    tour_points[user.id][tour.id] = calculate_submission_total_points(submission)
                else:
                    tour_points[user.id][tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'standings': standings,
        'tour_points': tour_points,
    }

    return render(request, 'predictions/contest/standings_tab.html', context)


def tour_card(request, tour_id):
    """Render a single tour card"""
    tour = get_object_or_404(
        TourNumber.objects.select_related('league').prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        ),
        id=tour_id,
    )

    submission = None
    match_predictions = {}
    prediction_tournament = PredictionsContestTournament.objects.filter(league=tour.league).first()
    if prediction_tournament:
        submission = (
            PredictionSubmission.objects.filter(user=request.user, tour=tour, tournament=prediction_tournament)
            .select_related('tournament')
            .prefetch_related(
                'predictions__match__result', 'predictions__match__team_home', 'predictions__match__team_guest'
            )
            .first()
        )
        if submission:
            match_predictions = {pred.match_id: pred for pred in submission.predictions.all()}

    context = {
        'tour': tour,
        'submission': submission,
        'match_predictions': match_predictions,
    }
    return render(request, 'predictions/contest/tour_card.html', context)


@login_required
def edit_predictions(request, tour_id):
    """Edit predictions for a specific tour"""
    tour = get_object_or_404(
        TourNumber.objects.select_related('league').prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        ),
        id=tour_id,
    )

    if not is_tour_open_for_predictions(tour):
        messages.error(request, 'Прогнозы для этого тура закрыты.')
        if request.htmx:
            return tour_card(request, tour_id)
        return redirect('predictions:main')

    prediction_tournament = PredictionsContestTournament.objects.filter(league=tour.league).first()
    if not prediction_tournament:
        messages.error(request, 'Этот турнир не доступен для прогнозов.')
        if request.htmx:
            return tour_card(request, tour_id)
        return redirect('predictions:main')

    submission, _ = PredictionSubmission.objects.get_or_create(
        user=request.user, tour=tour, tournament=prediction_tournament
    )

    matches = tour.tour_matches.all().order_by('id')

    existing_predictions = {pred.match_id: pred for pred in submission.predictions.all()}

    if request.method == 'POST':
        with transaction.atomic():
            for match in matches:
                prediction_value = request.POST.get(f'prediction_{match.id}')
                is_special = bool(request.POST.get(f'special_{match.id}'))

                existing_prediction = existing_predictions.get(match.id)

                if not prediction_value:
                    if existing_prediction:
                        existing_prediction.delete()
                else:
                    prediction, created = Prediction.objects.get_or_create(
                        submission=submission,
                        match=match,
                        defaults={'predicted_result': prediction_value, 'is_special': is_special},
                    )
                    if not created:
                        prediction.predicted_result = prediction_value
                        prediction.is_special = is_special
                        prediction.save()

            submission.save()

        if request.htmx:
            return tour_card(request, tour_id)

        return redirect('predictions:main')

    context = {
        'tour': tour,
        'matches': matches,
        'existing_predictions': existing_predictions,
        'submission': submission,
    }

    return render(request, 'predictions/contest/edit_predictions.html', context)


def preseason(request):
    selected_season, _ = resolve_selected_season(request)
    selected_tournament, tournament_form = resolve_selected_preseason_tournament(request, season=selected_season)
    context = {
        'selected_tournament': selected_tournament,
        'tournament_form': tournament_form,
    }

    only_tabs = request.GET.get('only_tabs', False)
    if only_tabs:
        return render(request, 'predictions/preseason/container.html#preseason-tabs', context)

    return render(request, 'predictions/preseason/container.html', context)


def preseason_my_tab(request, selected_tournament=None):
    if not request.user.is_authenticated:
        return render(request, 'predictions/preseason/my_predictions_tab.html', {'user': request.user})

    selected_tournament, _ = resolve_selected_preseason_tournament(request, selected_tournament)
    submission = None
    items = []
    league_teams = []
    if selected_tournament:
        league = selected_tournament.league
        league_teams = list(league.teams.all().order_by('title'))
        submission = (
            PreseasonPredictionSubmission.objects.filter(user=request.user, tournament=selected_tournament)
            .prefetch_related('items__team')
            .first()
        )
        if submission:
            items = list(submission.items.all().order_by('position'))

    context = {
        'selected_tournament': selected_tournament,
        'submission': submission,
        'items': items,
        'league_teams': league_teams,
    }
    return render(request, 'predictions/preseason/my_predictions_tab.html', context)


def _aggregate_preseason_results(tournament: PreseasonPredictionsTournament):
    # Returns list of dicts: {team, avg_position, counts: {position: count}}

    league = tournament.league
    teams = list(league.teams.all())
    team_ids = [t.id for t in teams]
    team_map = {t.id: t for t in teams}

    submissions = (
        PreseasonPredictionSubmission.objects.filter(tournament=tournament).prefetch_related('items__team').all()
    )

    positions_counts = {tid: defaultdict(int) for tid in team_ids}
    positions_sum = {tid: 0 for tid in team_ids}
    submissions_count = 0

    for sub in submissions:
        for item in sub.items.all():
            team_id = item.team_id
            pos = item.position
            positions_counts[team_id][pos] += 1
            positions_sum[team_id] += pos
        submissions_count += 1

    results = []
    if submissions_count > 0:
        for team_id in team_ids:
            avg = positions_sum[team_id] / submissions_count
            # Convert counts to a dense array
            histogram = [positions_counts[team_id].get(i, 0) for i in range(1, len(teams) + 1)]
            total = sum(histogram)
            results.append({'team': team_map[team_id], 'avg_position': avg, 'histogram': histogram, 'total': total})

        results.sort(key=lambda r: r['avg_position'])

    return results


def preseason_results_tab(request):
    selected_tournament, _ = resolve_selected_preseason_tournament(request)
    results = []
    submissions_count = 0
    if selected_tournament:
        results = _aggregate_preseason_results(selected_tournament)
        submissions_count = PreseasonPredictionSubmission.objects.filter(tournament=selected_tournament).count()

    context = {
        'selected_tournament': selected_tournament,
        'results': results,
        'submissions_count': submissions_count,
    }
    return render(request, 'predictions/preseason/results_tab.html', context)


def preseason_ranking_tab(request):
    selected_tournament, _ = resolve_selected_preseason_tournament(request)
    ranking_rows = []
    actual_positions = {}
    teams_count = 0
    has_played_matches = False

    if selected_tournament:
        league = selected_tournament.league
        teams_count = league.teams.count()
        actual_positions = get_teams_actual_positions(league)

        if actual_positions:
            has_played_matches = True
            submissions = (
                PreseasonPredictionSubmission.objects.filter(tournament=selected_tournament)
                .select_related('user__user_profile')
                .prefetch_related('items__team')
            )

            for submission in submissions:
                total_points, exact_hits, near_hits, items = calculate_preseason_submission_points(
                    submission, actual_positions, teams_count
                )
                ranking_rows.append(
                    {
                        'user': submission.user,
                        'total_points': total_points,
                        'exact_hits': exact_hits,
                        'near_hits': near_hits,
                        'updated': submission.updated,
                        'items': items,
                    }
                )

            ranking_rows.sort(
                key=lambda row: (
                    -row['total_points'],
                    -row['exact_hits'],
                    -row['near_hits'],
                    row['updated'],
                )
            )
            for i, row in enumerate(ranking_rows):
                row['place'] = i + 1

    context = {
        'selected_tournament': selected_tournament,
        'ranking_rows': ranking_rows,
        'actual_positions': actual_positions,
        'teams_count': teams_count,
        'has_played_matches': has_played_matches,
    }
    return render(request, 'predictions/preseason/ranking_tab.html', context)


@login_required
@require_POST
@transaction.atomic
def preseason_save(request):
    tournament_id = request.POST.get('tournament_id')
    selected_tournament = PreseasonPredictionsTournament.objects.filter(pk=tournament_id).first()

    order = request.POST.get('order')
    if not order:
        return preseason_my_tab(request, selected_tournament)

    team_ids = [int(x) for x in order.split(',') if x.strip()]
    league_team_ids = set(selected_tournament.league.teams.values_list('id', flat=True))
    if not set(team_ids).issubset(league_team_ids):
        messages.error(request, 'Содержатся команды вне выбранного турнира.')
        return preseason_my_tab(request, selected_tournament)

    submission, _ = PreseasonPredictionSubmission.objects.get_or_create(
        user=request.user, tournament=selected_tournament
    )
    submission.items.all().delete()
    PreseasonPredictionItem.objects.bulk_create(
        [
            PreseasonPredictionItem(submission=submission, team_id=tid, position=idx + 1)
            for idx, tid in enumerate(team_ids)
        ]
    )
    submission.save()

    response = preseason_my_tab(request, selected_tournament)
    response = trigger_client_event(response, 'prediction-saved', {'tournament_id': tournament_id})

    return response


def rewards_tab(request):
    """Tab for displaying rewards distribution"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)
    selected_tour, tour_form = resolve_selected_tour(request, selected_tournament)

    tour_rewards_data = {}
    if selected_tour:
        rewards_data = calculate_tour_rewards(selected_tour, selected_tournament)
        tour_rewards_data = {'tour': selected_tour, 'rewards': rewards_data}

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'tour_form': tour_form,
        'selected_tour': selected_tour,
        'tour_rewards_data': tour_rewards_data,
    }

    return render(request, 'predictions/contest/rewards_tab.html', context)
