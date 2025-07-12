from datetime import time

from django.contrib.auth.models import User
from django.utils import timezone

from tournament.models import TourNumber

from .models import PredictionSubmission


def get_open_tours():
    """Get tours that are currently open for predictions"""
    open_tours = []
    for tour in TourNumber.objects.filter(league__prediction_tournament__is_active=True).select_related('league'):
        # Check if tour is open for predictions
        if is_tour_open_for_predictions(tour):
            open_tours.append(tour.id)

    return open_tours


def is_tour_open_for_predictions(tour):
    """Check if a tour is currently open for predictions"""
    now = timezone.now()
    today = now.date()

    # Tour opens 3 days before start date
    open_date = tour.date_from - timezone.timedelta(days=3)

    # Tour closes at 18:00 on the start date
    close_datetime = timezone.datetime.combine(tour.date_from, time(18, 0))
    close_datetime = timezone.make_aware(close_datetime)

    return open_date <= today and now <= close_datetime


def get_user_tour_points(user, tour, tournament):
    """Get total points for a user in a specific tour"""
    submission = PredictionSubmission.objects.filter(user=user, tour=tour, tournament=tournament).first()
    if submission:
        return sum(prediction.points_earned for prediction in submission.predictions.all())
    return None


def get_user_tournament_total_points(user, tournament):
    """Get total points for a user in a tournament"""
    submissions = PredictionSubmission.objects.filter(user=user, tournament=tournament)

    total_points = 0
    for submission in submissions:
        total_points += sum(prediction.points_earned for prediction in submission.predictions.all())

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    # Get all users who have made predictions in this tournament
    users_with_predictions = User.objects.filter(prediction_submissions__tournament=tournament).distinct()

    standings = []
    for user in users_with_predictions:
        total_points = get_user_tournament_total_points(user, tournament)
        standings.append({'user': user, 'total_points': total_points})

    # Sort by total points (descending)
    standings.sort(key=lambda x: x['total_points'], reverse=True)

    # Add place
    for i, standing in enumerate(standings):
        standing['place'] = i + 1

    return standings
