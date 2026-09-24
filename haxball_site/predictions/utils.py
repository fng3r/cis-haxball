from datetime import time
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from .models import MatchPredictionOutcome, PredictionsContestTournament, PredictionSubmission
from .points_service import (
    calculate_avg_coefficient,
    calculate_roi,
    calculate_submission_predictions_counts,
    calculate_submission_total_points,
    is_prediction_correct,
    is_prediction_void,
)


def build_match_offers_map(tour):
    """Return mapping {match_id: MatchPredictionOffer} for matches of a tour.

    Uses the offer prefetched on tour's matches, so requires the queryset to
    prefetch 'tour_matches__prediction_offer' to avoid N+1 queries.
    """
    offers = {}
    for match in tour.tour_matches.all():
        offer = getattr(match, 'prediction_offer', None)
        if offer is not None:
            offers[match.id] = offer
    return offers


def build_match_outcomes_map(tour):
    """Return mapping {match_id: list of MatchPredictionOutcome} for a tour.

    Single unified map for all markets, ordered by market group (results,
    handicaps, totals, individual totals), id order within a group.
    Requires prefetching 'tour_matches__prediction_offer__outcomes' to
    avoid N+1 queries.
    """
    order = MatchPredictionOutcome.MARKET_ORDER
    outcomes = {}
    for match in tour.tour_matches.all():
        offer = getattr(match, 'prediction_offer', None)
        if offer is None or not getattr(offer, 'is_published', True):
            continue
        match_outcomes = sorted(
            offer.outcomes.all(),
            key=lambda o: (
                order.index(o.market) if o.market in order else 99,
                getattr(o, 'id', 0) or 0,
            ),
        )
        if match_outcomes:
            outcomes[match.id] = match_outcomes
    return outcomes


def build_match_outcome_groups_map(tour):
    """Return mapping {match_id: {market: [outcomes]}} for rendering grouped forms."""
    groups = {}
    for match_id, match_outcomes in build_match_outcomes_map(tour).items():
        market_groups = {}
        for outcome in match_outcomes:
            market_groups.setdefault(outcome.market, []).append(outcome)
        groups[match_id] = market_groups
    return groups


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
    start_datetime = timezone.datetime.combine(tour.date_from, time(20, 0))
    start_datetime = timezone.make_aware(start_datetime)

    return start_datetime


def get_user_tour_points(user, tour, tournament):
    """Get total points for a user in a specific tour"""
    submission = (
        PredictionSubmission.objects.filter(user=user, tour=tour, tournament=tournament)
        .select_related('tournament')
        .prefetch_related('predictions__match__result')
        .first()
    )
    if submission:
        return calculate_submission_total_points(submission)
    return None


def get_user_tournament_total_points(user, tournament):
    """Get total points for a user in a tournament"""
    submissions = (
        PredictionSubmission.objects.filter(user=user, tournament=tournament)
        .select_related('tournament')
        .prefetch_related('predictions__match__result')
    )

    total_points = 0
    for submission in submissions:
        total_points += calculate_submission_total_points(submission)

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    users_with_predictions = (
        User.objects.filter(prediction_submissions__tournament=tournament).select_related('user_profile').distinct()
    )

    all_submissions = (
        PredictionSubmission.objects.filter(tournament=tournament)
        .select_related('tournament')
        .prefetch_related('predictions__match__result', 'predictions__outcome')
    )

    submissions_by_user = {}
    for submission in all_submissions:
        if submission.user_id not in submissions_by_user:
            submissions_by_user[submission.user_id] = []
        submissions_by_user[submission.user_id].append(submission)

    is_coefficient = (
        tournament.scoring_method == PredictionsContestTournament.ScoringMethod.COEFFICIENT
    )
    standings = []
    for user in users_with_predictions:
        user_submissions = submissions_by_user.get(user.id, [])
        total_points = 0
        total_correct_predictions = 0
        total_predictions = 0
        coefficient_sum = Decimal('0')
        decisive_predictions = 0
        win_coefficient_sum = Decimal('0')
        win_coefficient_count = 0
        for submission in user_submissions:
            total_points += calculate_submission_total_points(submission)
            correct_predictions, predictions = calculate_submission_predictions_counts(submission)
            total_correct_predictions += correct_predictions
            total_predictions += predictions
            if is_coefficient:
                for prediction in submission.predictions.all():
                    # Voided stakes (tech defeats, totals on the line) are
                    # refunded: excluded from both ROI turnover and avg coeff.
                    if not prediction.match.is_played or not prediction.outcome_id:
                        continue
                    if is_prediction_void(prediction):
                        continue
                    coefficient_sum += prediction.outcome.coefficient
                    decisive_predictions += 1
                    if is_prediction_correct(prediction):
                        win_coefficient_sum += prediction.outcome.coefficient
                        win_coefficient_count += 1
        accuracy = total_correct_predictions / total_predictions * 100 if total_predictions > 0 else 0
        roi = (
            calculate_roi(total_points, tournament.nominal_points, decisive_predictions)
            if is_coefficient
            else None
        )
        avg_coefficient = calculate_avg_coefficient(coefficient_sum, decisive_predictions)
        avg_win_coefficient = calculate_avg_coefficient(win_coefficient_sum, win_coefficient_count)

        standings.append(
            {
                'user': user,
                'total_points': total_points,
                'accuracy': accuracy,
                'roi': roi,
                'avg_coefficient': avg_coefficient,
                'avg_win_coefficient': avg_win_coefficient,
            }
        )

    standings.sort(key=lambda x: (x['total_points'], x['accuracy']), reverse=True)

    for i, standing in enumerate(standings):
        standing['place'] = i + 1

    return standings


def calculate_tour_rewards(tour, tournament):
    """Calculate rewards distribution for a specific tour in predictions"""
    submissions = (
        PredictionSubmission.objects.filter(tour=tour, tournament=tournament)
        .select_related('tournament')
        .prefetch_related('predictions__match__result', 'user__user_profile')
    )

    if not submissions.exists():
        return {'total_participants': 0, 'total_prize_pool': 0, 'user_rewards': []}

    total_participants = submissions.count()
    total_prize_pool = total_participants * 10

    user_points = []
    for submission in submissions:
        points = calculate_submission_total_points(submission)
        user_points.append({'user': submission.user, 'points': points})

    total_points = sum(up['points'] for up in user_points if up['points'] >= 0)

    user_rewards = []
    for up in user_points:
        if up['points'] < 0:
            reward_amount = Decimal('0.00')
        elif total_points > 0:
            proportion = up['points'] / total_points
            reward_amount = Decimal(str(total_prize_pool)) * Decimal(str(proportion))
            reward_amount = reward_amount.quantize(Decimal('0.01'))
        else:
            reward_amount = Decimal('0.00')

        user_rewards.append({'user': up['user'], 'points': up['points'], 'reward_amount': reward_amount})

    user_rewards.sort(key=lambda x: x['points'], reverse=True)

    return {
        'total_participants': total_participants,
        'total_prize_pool': total_prize_pool,
        'user_rewards': user_rewards,
    }
