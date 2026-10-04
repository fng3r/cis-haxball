from datetime import time
from decimal import ROUND_DOWN, Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from tournament.models import TournamentStage, TourNumber

from .models import MatchPredictionOutcome, PredictionsContestTournament, PredictionSubmission
from .points_service import (
    calculate_avg_coefficient,
    calculate_prediction_points,
    calculate_roi,
    calculate_submission_predictions_counts,
    calculate_submission_total_points,
    is_prediction_correct,
    is_prediction_void,
)


def get_regular_tours(league):
    """League tours excluding playoffs (stage type), ordered by number."""
    return (
        TourNumber.objects.filter(league=league)
        .exclude(stage__type=TournamentStage.StageType.PLAYOFF)
        .order_by('number')
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
        .exclude(tour__stage__type=TournamentStage.StageType.PLAYOFF)
        .select_related('tournament')
        .prefetch_related('predictions__match__result', 'predictions__outcome')
    )

    submissions_by_user = {}
    for submission in all_submissions:
        if submission.user_id not in submissions_by_user:
            submissions_by_user[submission.user_id] = []
        submissions_by_user[submission.user_id].append(submission)

    is_coefficient = tournament.scoring_method == PredictionsContestTournament.ScoringMethod.COEFFICIENTS
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
        roi = calculate_roi(total_points, tournament.nominal_points, decisive_predictions) if is_coefficient else None
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
    """Calculate rewards distribution for a specific tour in predictions.

    Classic tournaments keep the proportional split; coefficients
    tournaments use the hybrid scheme (even base + rank-weighted place
    slice, see _calculate_hybrid_tour_rewards).
    """
    submissions = (
        PredictionSubmission.objects.filter(tour=tour, tournament=tournament)
        .select_related('tournament')
        .prefetch_related('predictions__match__result', 'user__user_profile')
    )

    if not submissions.exists():
        return {'total_participants': 0, 'total_prize_pool': 0, 'user_rewards': []}

    total_participants = submissions.count()
    total_prize_pool = total_participants * tournament.prize_pool_contribution

    user_points = []
    for submission in submissions:
        points = calculate_submission_total_points(submission)
        user_points.append({'user': submission.user, 'points': points})

    if tournament.scoring_method == PredictionsContestTournament.ScoringMethod.CLASSIC:
        return _calculate_proportional_tour_rewards(user_points, total_participants, total_prize_pool)
    return _calculate_hybrid_tour_rewards(user_points, total_participants, total_prize_pool)


def _calculate_proportional_tour_rewards(user_points, total_participants, total_prize_pool):
    """Legacy proportional split (classic tournaments only)."""
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


# Square-root rank weights: smooth decay, scale-free, top-favoring yet even
# (1st vs 25th = 5x, vs 10x harmonic).
def _place_weight(rank):
    return Decimal(1) / Decimal(rank).sqrt()


BASE_SLICE = Decimal('0.5')
PLACE_SLICE = Decimal('0.5')


def _calculate_hybrid_tour_rewards(user_points, total_participants, total_prize_pool):
    """Hybrid split for coefficients tournaments.

    50% of the pool is shared evenly among all participants; 50% goes to
    eligible users (strictly positive tour balance) by place weights,
    renormalized to the used weights. Tied users pool the occupied places'
    weights and split them evenly. Rounding remainder goes to 1st place.
    """
    pool = Decimal(total_prize_pool)
    ranked = sorted(user_points, key=lambda entry: entry['points'], reverse=True)

    # Competition ranking ("1, 2, 2, 4"): equal points share pooled weights.
    position = 1
    index = 0
    while index < len(ranked):
        end = index
        while end < len(ranked) and ranked[end]['points'] == ranked[index]['points']:
            end += 1
        group = ranked[index:end]
        if ranked[index]['points'] > 0:
            ranks = range(position, position + len(group))
            pooled_weight = sum((_place_weight(rank) for rank in ranks), Decimal('0'))
            for entry in group:
                entry['place_weight'] = pooled_weight / len(group)
        else:
            for entry in group:
                entry['place_weight'] = Decimal('0')
        position += len(group)
        index = end

    used_weights = sum(entry['place_weight'] for entry in ranked)
    if used_weights > 0:
        base_each = pool * BASE_SLICE / total_participants
        place_slice = pool * PLACE_SLICE
    else:
        # Nobody eligible: the whole pool is shared evenly.
        base_each = pool / total_participants
        place_slice = Decimal('0')

    distributed = Decimal('0')
    user_rewards = []
    for entry in ranked:
        base_amount = base_each
        if used_weights > 0:
            place_amount = place_slice * entry['place_weight'] / used_weights
        else:
            place_amount = Decimal('0')
        reward_amount = (base_amount + place_amount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        distributed += reward_amount
        user_rewards.append(
            {
                'user': entry['user'],
                'points': entry['points'],
                'base_amount': base_amount.quantize(Decimal('0.01'), rounding=ROUND_DOWN),
                'place_amount': place_amount.quantize(Decimal('0.01'), rounding=ROUND_DOWN),
                'reward_amount': reward_amount,
            }
        )

    # Rounding remainder goes to the top-ranked participant.
    remainder = pool - distributed
    if remainder > 0 and user_rewards:
        user_rewards[0]['reward_amount'] += remainder

    return {
        'total_participants': total_participants,
        'total_prize_pool': total_prize_pool,
        'user_rewards': user_rewards,
    }


def collect_tour_prediction_stats(tour, tournament, submissions, matches):
    """Aggregate per-tour statistics for coefficient-based predictions.

    `submissions` — PredictionSubmission list for (tournament, tour) with
    prefetched predictions__outcome and predictions__match.
    `matches` — Match list of the tour with team_home/guest, result,
    prediction_offer__outcomes prefetched.

    Returns dict with tour-level aggregates (participants, accuracy,
    best/worst user, biggest win, highest coefficients) and per-match
    breakdowns (popularity, hit rate, avg coefficient).
    """
    matches_by_id = {match.id: match for match in matches}

    user_points = []
    for submission in submissions:
        user_points.append({'user': submission.user, 'points': calculate_submission_total_points(submission)})
    user_points.sort(key=lambda entry: entry['points'], reverse=True)

    participants = len(submissions)
    total_predictions = sum(len(list(sub.predictions.all())) for sub in submissions)

    decisive = 0
    correct = 0
    void_count = 0

    biggest_win = None
    biggest_win_users = []
    highest_coef_hit = None
    highest_coef_picked = None

    picks_by_match = {match_id: [] for match_id in matches_by_id}
    for submission in submissions:
        for prediction in submission.predictions.all():
            match = getattr(prediction, 'match', None)
            match_id = getattr(prediction, 'match_id', None) or (match.id if match else None)
            if match_id not in picks_by_match:
                continue
            points = calculate_prediction_points(prediction, tournament=tournament)
            picks_by_match[match_id].append({'prediction': prediction, 'points': points, 'user': submission.user})

            outcome = getattr(prediction, 'outcome', None)
            coefficient = outcome.coefficient if outcome is not None else None

            if match is not None and match.is_played and outcome is not None:
                if is_prediction_void(prediction):
                    void_count += 1
                else:
                    decisive += 1
                    if is_prediction_correct(prediction):
                        correct += 1

            if coefficient is not None:
                label = outcome.display_label if outcome is not None else ''
                if highest_coef_picked is None or coefficient > highest_coef_picked['coefficient']:
                    highest_coef_picked = {
                        'user': submission.user,
                        'coefficient': coefficient,
                        'outcome_label': label,
                        'match': match,
                        'is_correct': is_prediction_correct(prediction) if match and match.is_played else None,
                    }
                if (
                    match is not None
                    and match.is_played
                    and is_prediction_correct(prediction)
                    and (highest_coef_hit is None or coefficient > highest_coef_hit['coefficient'])
                ):
                    highest_coef_hit = {
                        'user': submission.user,
                        'coefficient': coefficient,
                        'outcome_label': label,
                        'match': match,
                        'points': points,
                    }

            if (
                points is not None
                and match is not None
                and match.is_played
                and outcome is not None
                and not is_prediction_void(prediction)
                and points > 0
            ):
                if biggest_win is None or points > biggest_win['points']:
                    biggest_win = {
                        'user': submission.user,
                        'points': points,
                        'coefficient': coefficient,
                        'outcome_label': outcome.display_label,
                        'match': match,
                    }
                    biggest_win_users = [submission.user]
                elif points == biggest_win['points']:
                    biggest_win_users.append(submission.user)

    accuracy = (correct / decisive * 100) if decisive else None
    total_points = sum((entry['points'] for entry in user_points), Decimal('0'))
    avg_points = (total_points / participants) if participants else None

    if user_points:
        best_points = user_points[0]['points']
        worst_points = user_points[-1]['points']
        best_users = [entry['user'] for entry in user_points if entry['points'] == best_points]
        worst_users = [entry['user'] for entry in user_points if entry['points'] == worst_points]
    else:
        best_points = None
        worst_points = None
        best_users = []
        worst_users = []

    match_stats = []
    for match in matches:
        picks = picks_by_match.get(match.id, [])
        total_picks = len(picks)

        counts = {}
        outcome_objs = {}
        for entry in picks:
            outcome = getattr(entry['prediction'], 'outcome', None)
            if outcome is None:
                continue
            counts[outcome.id] = counts.get(outcome.id, 0) + 1
            outcome_objs[outcome.id] = outcome

        offer = getattr(match, 'prediction_offer', None)
        if offer is not None:
            try:
                offer_outcomes = list(offer.outcomes.all())
            except Exception:
                offer_outcomes = []
            for outcome in offer_outcomes:
                outcome_objs.setdefault(outcome.id, outcome)
                counts.setdefault(outcome.id, 0)

        outcome_rows = []
        match_correct = 0
        match_decisive = 0
        match_points_total = Decimal('0')
        match_best_points = None
        match_best_users = []
        coef_sum = Decimal('0')
        coef_count = 0
        for outcome_id, outcome in outcome_objs.items():
            count = counts.get(outcome_id, 0)
            pct = (count / total_picks * 100) if total_picks else 0
            settled = outcome.settle(match) if match.is_played else None
            outcome_rows.append(
                {
                    'outcome': outcome,
                    'count': count,
                    'pct': pct,
                    'is_winning': settled,
                }
            )
            if outcome.coefficient is not None and count:
                coef_sum += outcome.coefficient * count
                coef_count += count

        outcome_rows.sort(key=lambda row: (-row['count'], str(row['outcome'].display_label)))

        for entry in picks:
            prediction = entry['prediction']
            if not match.is_played or not getattr(prediction, 'outcome_id', None):
                continue
            if is_prediction_void(prediction):
                continue
            match_decisive += 1
            if is_prediction_correct(prediction):
                match_correct += 1
            match_points_total += entry['points']
            if match_best_points is None or entry['points'] > match_best_points:
                match_best_points = entry['points']
                match_best_users = [entry['user']]
            elif entry['points'] == match_best_points:
                match_best_users.append(entry['user'])

        match_stats.append(
            {
                'match': match,
                'total_picks': total_picks,
                'decisive': match_decisive,
                'correct': match_correct,
                'accuracy': (match_correct / match_decisive * 100) if match_decisive else None,
                'avg_coefficient': (coef_sum / coef_count) if coef_count else None,
                'avg_points': (match_points_total / match_decisive) if match_decisive else None,
                'best_points': match_best_points,
                'best_users': match_best_users,
                'outcomes': outcome_rows,
                'top_outcome': outcome_rows[0] if outcome_rows and total_picks else None,
            }
        )

    decided = [m for m in match_stats if m['decisive']]
    most_predictable = max(decided, key=lambda m: m['accuracy']) if decided else None
    least_predictable = min(decided, key=lambda m: m['accuracy']) if decided else None
    most_profitable_match = max(decided, key=lambda m: m['avg_points']) if decided else None
    least_profitable_match = min(decided, key=lambda m: m['avg_points']) if decided else None

    return {
        'tour': tour,
        'participants': participants,
        'total_predictions': total_predictions,
        'decisive': decisive,
        'correct': correct,
        'void_count': void_count,
        'accuracy': accuracy,
        'total_points': total_points,
        'avg_points': avg_points,
        'best_points': best_points,
        'best_users': best_users,
        'worst_points': worst_points,
        'worst_users': worst_users,
        'user_points': user_points,
        'biggest_win': biggest_win,
        'biggest_win_users': biggest_win_users,
        'highest_coef_hit': highest_coef_hit,
        'highest_coef_picked': highest_coef_picked,
        'matches': match_stats,
        'most_predictable': most_predictable,
        'least_predictable': least_predictable,
        'most_profitable_match': most_profitable_match,
        'least_profitable_match': least_profitable_match,
    }


def collect_tours_overview(tournament, tours, submissions_by_tour):
    """Light per-tour summary across the whole tournament for the stats tab.

    `tours` should prefetch tour_matches (is_played is read to detect
    whether the tour has started). Stats stay hidden until the first
    match of the tour is played.
    """
    overview = []
    for tour in tours:
        submissions = submissions_by_tour.get(tour.id, [])
        participants = len(submissions)
        predictions = sum(len(list(sub.predictions.all())) for sub in submissions)
        has_played_matches = any(match.is_played for match in tour.tour_matches.all())
        decisive = 0
        correct = 0
        total_points = Decimal('0')
        best_points = None
        best_users = []
        worst_points = None
        worst_users = []
        for submission in submissions:
            points = calculate_submission_total_points(submission)
            total_points += points
            if best_points is None or points > best_points:
                best_points = points
                best_users = [submission.user]
            elif points == best_points:
                best_users.append(submission.user)
            if worst_points is None or points < worst_points:
                worst_points = points
                worst_users = [submission.user]
            elif points == worst_points:
                worst_users.append(submission.user)
            for prediction in submission.predictions.all():
                match = getattr(prediction, 'match', None)
                if match is not None and match.is_played and getattr(prediction, 'outcome_id', None):
                    if is_prediction_void(prediction):
                        continue
                    decisive += 1
                    if is_prediction_correct(prediction):
                        correct += 1
        overview.append(
            {
                'tour': tour,
                'participants': participants,
                'predictions': predictions,
                'has_played_matches': has_played_matches,
                'decisive': decisive,
                'accuracy': (correct / decisive * 100) if decisive else None,
                'avg_points': (total_points / participants) if participants else None,
                'best_points': best_points,
                'best_users': best_users,
                'worst_points': worst_points,
                'worst_users': worst_users,
            }
        )
    return overview
