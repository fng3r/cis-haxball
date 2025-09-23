from datetime import time

from django.contrib.auth.models import User
from django.utils import timezone

from .models import PredictionSubmission


def is_tour_open_for_predictions(tour):
    """Check if a tour is currently open for predictions"""
    now = timezone.localtime()

    closed_at = get_tour_start_datetime(tour)
    open_at = get_tour_opening_datetime(tour)

    return open_at <= now <= closed_at


def get_tour_opening_datetime(tour):
    start_datetime = get_tour_start_datetime(tour)

    return start_datetime - timezone.timedelta(days=3)


def get_tour_start_datetime(tour):
    start_datetime = timezone.datetime.combine(tour.date_from, time(18, 0))
    start_datetime = timezone.make_aware(start_datetime)

    return start_datetime


def get_user_tour_points(user, tour, tournament):
    """Get total points for a user in a specific tour"""
    submission = (
        PredictionSubmission.objects.filter(user=user, tour=tour, tournament=tournament)
        .prefetch_related('predictions__match__result')
        .first()
    )
    if submission:
        return submission.get_total_points()
    return None


def get_user_tournament_total_points(user, tournament):
    """Get total points for a user in a tournament"""
    submissions = PredictionSubmission.objects.filter(user=user, tournament=tournament).prefetch_related(
        'predictions__match__result'
    )

    total_points = 0
    for submission in submissions:
        total_points += submission.get_total_points()

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    users_with_predictions = (
        User.objects.filter(prediction_submissions__tournament=tournament).select_related('user_profile').distinct()
    )

    all_submissions = PredictionSubmission.objects.filter(tournament=tournament).prefetch_related(
        'predictions__match__result'
    )

    submissions_by_user = {}
    for submission in all_submissions:
        if submission.user_id not in submissions_by_user:
            submissions_by_user[submission.user_id] = []
        submissions_by_user[submission.user_id].append(submission)

    standings = []
    for user in users_with_predictions:
        user_submissions = submissions_by_user.get(user.id, [])
        total_points = 0
        for submission in user_submissions:
            total_points += submission.get_total_points()

        standings.append({'user': user, 'total_points': total_points})

    standings.sort(key=lambda x: x['total_points'], reverse=True)

    for i, standing in enumerate(standings):
        standing['place'] = i + 1

    return standings
