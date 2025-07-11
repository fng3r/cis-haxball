from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tournament.models import TourNumber

from .forms import TournamentFilterForm, UserFilterForm
from .models import Prediction, PredictionSubmission, PredictionTournament
from .utils import (
    get_open_tours,
    get_tournament_standings,
    get_user_tour_points,
    is_tour_closed_for_predictions,
    is_tour_open_for_predictions,
)


def get_default_tournament():
    """Get default tournament for predictions (first active tournament in current season)"""
    try:
        return PredictionTournament.objects.filter(is_active=True, league__championship__is_active=True).first()
    except:
        return None


def get_users_with_predictions(tournament=None):
    """Get users who have made at least one prediction"""
    if tournament:
        return User.objects.filter(prediction_submissions__tournament=tournament).distinct()
    return User.objects.filter(prediction_submissions__isnull=False).distinct()


@login_required
def predictions_main(request):
    """Main predictions page with three tabs"""
    default_tournament = get_default_tournament()
    selected_tournament = None
    selected_user = None

    # Determine selected tournament
    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    # Determine selected user
    if request.GET.get('user'):
        selected_user = User.objects.filter(pk=request.GET.get('user')).first()

    # Prepare forms with initial values
    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    active_tournaments = PredictionTournament.objects.filter(is_active=True)

    # Render the make_predictions_tab content for initial load
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


@login_required
def make_predictions_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making predictions"""
    default_tournament = get_default_tournament()
    if not selected_tournament:
        if request.GET.get('tournament'):
            selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
        elif default_tournament:
            selected_tournament = default_tournament
    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    user_predictions = {}
    if selected_tournament:
        tours = TourNumber.objects.filter(league=selected_tournament.league)
        for tour in tours:
            try:
                submission = PredictionSubmission.objects.get(
                    user=request.user, tour=tour, tournament=selected_tournament
                )
                user_predictions[tour.id] = submission
            except PredictionSubmission.DoesNotExist:
                user_predictions[tour.id] = None
    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'user_predictions': user_predictions,
    }
    if initial_context:
        return render_to_string('predictions/make_predictions_tab.html', context, request=request)
    return render(request, 'predictions/make_predictions_tab.html', context)


@login_required
def view_predictions_tab(request):
    """Tab for viewing other users' predictions"""
    # Get default tournament
    default_tournament = get_default_tournament()

    # Determine selected tournament
    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    # Determine selected user
    selected_user = None
    if request.GET.get('user'):
        selected_user = User.objects.filter(pk=request.GET.get('user')).first()
    elif get_users_with_predictions(selected_tournament):
        selected_user = get_users_with_predictions(selected_tournament).first()

    # Prepare forms with initial values
    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    # Update user form queryset to only include users with predictions
    if get_users_with_predictions(selected_tournament):
        user_form.fields['user'].queryset = get_users_with_predictions(selected_tournament)

    # Get predictions data
    predictions_data = {}
    if selected_tournament and selected_user:
        tours = TourNumber.objects.filter(league=selected_tournament.league)

        for tour in tours:
            try:
                submission = PredictionSubmission.objects.get(
                    user=selected_user, tour=tour, tournament=selected_tournament
                )
                # Only show predictions if tour is closed
                if is_tour_closed_for_predictions(tour):
                    predictions_data[tour.id] = submission
                else:
                    predictions_data[tour.id] = None  # Tour not closed yet
            except PredictionSubmission.DoesNotExist:
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


@login_required
def standings_tab(request):
    """Tab for tournament standings"""
    # Get default tournament
    default_tournament = get_default_tournament()

    # Determine selected tournament
    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = PredictionTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    # Prepare forms with initial values
    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    # Get standings data
    standings = []
    tour_points = {}

    if selected_tournament:
        standings = get_tournament_standings(selected_tournament)

        # Get points for each tour for each user
        tours = TourNumber.objects.filter(league=selected_tournament.league)

        for standing in standings:
            user = standing['user']
            tour_points[user.id] = {}
            for tour in tours:
                tour_points[user.id][tour.id] = get_user_tour_points(user, tour, selected_tournament)

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'standings': standings,
        'tour_points': tour_points,
    }

    return render(request, 'predictions/standings_tab.html', context)


@login_required
def tour_card(request, tour_id):
    """Render a single tour card"""
    tour = get_object_or_404(TourNumber, id=tour_id)

    submission = None
    try:
        prediction_tournament = PredictionTournament.objects.get(league=tour.league)
        submission = PredictionSubmission.objects.get(user=request.user, tour=tour, tournament=prediction_tournament)
    except (PredictionTournament.DoesNotExist, PredictionSubmission.DoesNotExist):
        submission = None

    context = {
        'tour': tour,
        'submission': submission,
    }
    return render(request, 'predictions/tour_card.html', context)


@login_required
def edit_predictions(request, tour_id):
    """Edit predictions for a specific tour"""
    tour = get_object_or_404(TourNumber, id=tour_id)

    # Check if tour is open for predictions
    if not is_tour_open_for_predictions(tour):
        messages.error(request, 'Прогнозы для этого тура закрыты.')
        if request.htmx:
            # Return tour card content for HTMX requests
            return tour_card(request, tour_id)
        return redirect('predictions:main')

    # Get or create prediction tournament
    try:
        prediction_tournament = PredictionTournament.objects.get(league=tour.league)
    except PredictionTournament.DoesNotExist:
        messages.error(request, 'Этот турнир не доступен для прогнозов.')
        if request.htmx:
            # Return tour card content for HTMX requests
            return tour_card(request, tour_id)
        return redirect('predictions:main')

    # Get or create submission
    submission, created = PredictionSubmission.objects.get_or_create(
        user=request.user, tour=tour, tournament=prediction_tournament
    )

    # Get matches for this tour
    matches = tour.tour_matches.all().order_by('id')

    # Get existing predictions
    existing_predictions = {pred.match_id: pred for pred in submission.predictions.all()}

    if request.method == 'POST':
        with transaction.atomic():
            # Process each match prediction
            for match in matches:
                prediction_value = request.POST.get(f'prediction_{match.id}')

                # Check if prediction exists for this match
                existing_prediction = existing_predictions.get(match.id)

                if not prediction_value:
                    if existing_prediction:
                        existing_prediction.delete()
                else:
                    # Get or create prediction
                    prediction, created = Prediction.objects.get_or_create(
                        submission=submission, match=match, defaults={'predicted_result': prediction_value}
                    )
                    if not created:
                        prediction.predicted_result = prediction_value
                        prediction.save()

            messages.success(request, 'Прогнозы успешно сохранены!')

            # For HTMX requests, return the updated tour card
            if request.htmx:
                return tour_card(request, tour_id)

            # For regular requests, redirect to main
            return redirect('predictions:main')

    context = {
        'tour': tour,
        'matches': matches,
        'existing_predictions': existing_predictions,
        'submission': submission,
    }

    return render(request, 'predictions/edit_predictions.html', context)


@login_required
@require_POST
@csrf_exempt
def save_prediction_ajax(request):
    """AJAX endpoint for saving individual predictions"""
    match_id = request.POST.get('match_id')
    prediction_value = request.POST.get('prediction_value')
    tour_id = request.POST.get('tour_id')

    if not all([match_id, prediction_value, tour_id]):
        return JsonResponse({'success': False, 'error': 'Missing required parameters'})

    try:
        from tournament.models import Match

        match = Match.objects.get(id=match_id)
        tour = TourNumber.objects.get(id=tour_id)

        # Check if tour is open for predictions
        if not is_tour_open_for_predictions(tour):
            return JsonResponse({'success': False, 'error': 'Tour is closed for predictions'})

        # Get or create prediction tournament
        try:
            prediction_tournament = PredictionTournament.objects.get(league=tour.league)
        except PredictionTournament.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tournament not available for predictions'})

        # Get or create submission
        submission, created = PredictionSubmission.objects.get_or_create(
            user=request.user, tour=tour, tournament=prediction_tournament
        )

        # Get or create prediction
        prediction, pred_created = Prediction.objects.get_or_create(
            submission=submission, match=match, defaults={'predicted_result': prediction_value}
        )

        if not pred_created:
            prediction.predicted_result = prediction_value
            prediction.save()

        return JsonResponse({'success': True})

    except (Match.DoesNotExist, TourNumber.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Match or tour not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
