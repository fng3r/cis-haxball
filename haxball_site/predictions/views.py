from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from django_htmx.http import trigger_client_event

from tournament.models import TourNumber

from .forms import TournamentFilterForm, UserFilterForm
from .models import (
    LongTermPredictionItem,
    LongTermPredictionSubmission,
    Prediction,
    PredictionSubmission,
    PredictionTournament,
)
from .utils import (
    get_open_tours,
    get_tournament_standings,
    is_tour_open_for_predictions,
)


def get_default_tournament():
    return (
        PredictionTournament.objects.filter(is_active=True, league__championship__is_active=True)
        .select_related('league')
        .first()
    )


def get_users_with_predictions(tournament=None):
    """Get users who have made at least one prediction"""
    if tournament:
        return (
            User.objects.filter(prediction_submissions__tournament=tournament).select_related('user_profile').distinct()
        )
    return User.objects.filter(prediction_submissions__isnull=False).select_related('user_profile').distinct()


def predictions_main(request):
    """Main predictions page with three tabs"""
    default_tournament = get_default_tournament()
    selected_tournament = None
    selected_user = None

    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    active_tournaments = PredictionTournament.objects.filter(is_active=True)

    make_predictions_tab_html = make_predictions_tab(
        request, initial_context=True, selected_tournament=selected_tournament
    )

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'active_tournaments': active_tournaments,
        'make_predictions_tab_html': make_predictions_tab_html,
    }
    return render(request, 'predictions/main.html', context)


def make_predictions_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making predictions"""
    if not request.user.is_authenticated:
        return render_to_string(
            'predictions/contest/make_predictions_tab.html',
            {'user': request.user},
            request=request,
        )

    default_tournament = get_default_tournament()
    if not selected_tournament:
        if request.GET.get('tournament'):
            selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
        elif default_tournament:
            selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            PredictionTournament.objects.filter(pk=selected_tournament.pk)
            .select_related('league')
            .prefetch_related(
                'league__tours__tour_matches__team_home',
                'league__tours__tour_matches__team_guest',
                'league__tours__tour_matches__result',
            )
            .first()
        )

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    user_predictions = {}
    if selected_tournament:
        tours = TourNumber.objects.filter(league=selected_tournament.league).prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        )

        submissions = PredictionSubmission.objects.filter(
            user=request.user, tournament=selected_tournament
        ).prefetch_related('predictions__match__result')

        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission:
                match_predictions = {pred.match_id: pred for pred in submission.predictions.all()}
                user_predictions[tour.id] = {'submission': submission, 'match_predictions': match_predictions}
            else:
                user_predictions[tour.id] = {'submission': None, 'match_predictions': {}}

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'user_predictions': user_predictions,
        'user': request.user,
    }
    if initial_context:
        return render_to_string('predictions/contest/make_predictions_tab.html', context, request=request)
    return render(request, 'predictions/contest/make_predictions_tab.html', context)


def view_predictions_tab(request):
    """Tab for viewing other users' predictions"""
    default_tournament = get_default_tournament()

    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            PredictionTournament.objects.filter(pk=selected_tournament.pk)
            .prefetch_related(
                'league__tours__tour_matches__team_home',
                'league__tours__tour_matches__team_guest',
                'league__tours__tour_matches__result',
            )
            .first()
        )

    user_id = request.GET.get('user')
    selected_user = None
    if user_id:
        selected_user = User.objects.filter(pk=user_id).first()
    elif get_users_with_predictions(selected_tournament):
        selected_user = get_users_with_predictions(selected_tournament).first()
    if not selected_user:
        selected_user = User.objects.first()

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    if get_users_with_predictions(selected_tournament):
        user_form.fields['user'].queryset = get_users_with_predictions(selected_tournament)

    predictions_data = {}
    if selected_tournament and selected_user:
        tours = TourNumber.objects.filter(league=selected_tournament.league).prefetch_related(
            'tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result'
        )

        submissions = PredictionSubmission.objects.filter(
            user=selected_user, tournament=selected_tournament
        ).prefetch_related(
            'predictions__match__result__winner', 'predictions__match__team_home', 'predictions__match__team_guest'
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission and not is_tour_open_for_predictions(tour):
                predictions_data[tour.id] = submission
            else:
                predictions_data[tour.id] = None

    open_tours = get_open_tours()

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'selected_user': selected_user,
        'predictions_data': predictions_data,
        'open_tours': open_tours,
    }

    return render(request, 'predictions/contest/view_predictions_tab.html', context)


def standings_tab(request):
    """Tab for tournament standings"""
    default_tournament = get_default_tournament()

    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            PredictionTournament.objects.filter(pk=selected_tournament.pk)
            .prefetch_related(
                'league__tours__tour_matches__team_home',
                'league__tours__tour_matches__team_guest',
                'league__tours__tour_matches__result',
            )
            .first()
        )

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    standings = []
    tour_points = {}

    if selected_tournament:
        standings = get_tournament_standings(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league)

        all_submissions = PredictionSubmission.objects.filter(tournament=selected_tournament).prefetch_related(
            'predictions__match__result'
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
                    tour_points[user.id][tour.id] = submission.get_total_points()
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
    prediction_tournament = PredictionTournament.objects.filter(league=tour.league).first()
    if prediction_tournament:
        submission = (
            PredictionSubmission.objects.filter(user=request.user, tour=tour, tournament=prediction_tournament)
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

    prediction_tournament = PredictionTournament.objects.filter(league=tour.league).first()
    if not prediction_tournament:
        messages.error(request, 'Этот турнир не доступен для прогнозов.')
        if request.htmx:
            return tour_card(request, tour_id)
        return redirect('predictions:main')

    submission, created = PredictionSubmission.objects.get_or_create(
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


def longterm(request):
    selected_tournament = _resolve_selected_tournament(request)
    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    context = {
        'selected_tournament': selected_tournament,
        'tournament_form': tournament_form,
    }
    return render(request, 'predictions/longterm/container.html', context)


def longterm_my_tab(request):
    if not request.user.is_authenticated:
        return render(request, 'predictions/longterm/my_predictions_tab.html', {'user': request.user})

    selected_tournament = _resolve_selected_tournament(request)
    submission = None
    items = []
    league_teams = []
    if selected_tournament:
        league = selected_tournament.league
        league_teams = list(league.teams.all().order_by('title'))
        submission = (
            LongTermPredictionSubmission.objects.filter(user=request.user, tournament=selected_tournament)
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
    return render(request, 'predictions/longterm/my_predictions_tab.html', context)


def _resolve_selected_tournament(request):
    selected_tournament = None
    if not selected_tournament:
        if request.GET.get('tournament'):
            selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
        else:
            selected_tournament = get_default_tournament()

    return selected_tournament


def _aggregate_longterm_results(tournament: PredictionTournament):
    # Returns list of dicts: {team, avg_position, counts: {position: count}}

    league = tournament.league
    teams = list(league.teams.all())
    team_ids = [t.id for t in teams]
    team_map = {t.id: t for t in teams}

    submissions = (
        LongTermPredictionSubmission.objects.filter(tournament=tournament).prefetch_related('items__team').all()
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
    for team_id in team_ids:
        if submissions_count > 0:
            avg = positions_sum[team_id] / submissions_count
        else:
            avg = None
        # Convert counts to a dense array
        histogram = [positions_counts[team_id].get(i, 0) for i in range(1, len(teams) + 1)]
        total = sum(histogram)
        results.append({'team': team_map[team_id], 'avg_position': avg, 'histogram': histogram, 'total': total})

    results.sort(key=lambda r: r['avg_position'])
    return results


def longterm_results_tab(request):
    selected_tournament = _resolve_selected_tournament(request)
    results = []
    if selected_tournament:
        results = _aggregate_longterm_results(selected_tournament)

    context = {
        'selected_tournament': selected_tournament,
        'results': results,
    }
    return render(request, 'predictions/longterm/results_tab.html', context)


@login_required
@require_POST
@transaction.atomic
def longterm_save(request):
    tournament_id = request.POST.get('tournament_id')
    selected_tournament = PredictionTournament.objects.filter(pk=tournament_id).first()

    order = request.POST.get('order')
    if not order:
        return longterm_my_tab(request)

    team_ids = [int(x) for x in order.split(',') if x.strip()]
    league_team_ids = set(selected_tournament.league.teams.values_list('id', flat=True))
    if not set(team_ids).issubset(league_team_ids):
        messages.error(request, 'Содержатся команды вне выбранного турнира.')
        return longterm_my_tab(request)

    submission, _ = LongTermPredictionSubmission.objects.get_or_create(
        user=request.user, tournament=selected_tournament
    )
    submission.items.all().delete()
    LongTermPredictionItem.objects.bulk_create(
        [
            LongTermPredictionItem(submission=submission, team_id=tid, position=idx + 1)
            for idx, tid in enumerate(team_ids)
        ]
    )

    response = longterm_my_tab(request)
    response = trigger_client_event(response, 'prediction-saved', {'tournament_id': tournament_id})

    return response
