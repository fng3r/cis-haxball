from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from tournament.models import TourNumber

from .forms import TournamentFilterForm, UserFilterForm
from .models import Prediction, PredictionSubmission, PredictionTournament
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

    if request.GET.get('user'):
        selected_user = User.objects.filter(pk=request.GET.get('user')).first()

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
        'selected_user': selected_user,
        'active_tournaments': active_tournaments,
        'make_predictions_tab_html': make_predictions_tab_html,
    }
    return render(request, 'predictions/main.html', context)


def make_predictions_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making predictions"""
    if not request.user.is_authenticated:
        return render_to_string('predictions/make_predictions_tab.html', {'user': request.user}, request=request)

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
        ).prefetch_related('predictions__match')

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
        return render_to_string('predictions/make_predictions_tab.html', context, request=request)
    return render(request, 'predictions/make_predictions_tab.html', context)


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

    selected_user = None
    if request.GET.get('user'):
        selected_user = User.objects.filter(pk=request.GET.get('user')).first()
    elif get_users_with_predictions(selected_tournament):
        selected_user = get_users_with_predictions(selected_tournament).first()

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

    return render(request, 'predictions/view_predictions_tab.html', context)


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
            'predictions'
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
                    tour_points[user.id][tour.id] = sum(pred.points_earned for pred in submission.predictions.all())
                else:
                    tour_points[user.id][tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'standings': standings,
        'tour_points': tour_points,
    }

    return render(request, 'predictions/standings_tab.html', context)


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
    return render(request, 'predictions/tour_card.html', context)


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

                existing_prediction = existing_predictions.get(match.id)

                if not prediction_value:
                    if existing_prediction:
                        existing_prediction.delete()
                else:
                    prediction, created = Prediction.objects.get_or_create(
                        submission=submission, match=match, defaults={'predicted_result': prediction_value}
                    )
                    if not created:
                        prediction.predicted_result = prediction_value
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

    return render(request, 'predictions/edit_predictions.html', context)
