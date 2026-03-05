from decimal import Decimal

from tournament.models import MatchResult
from tournament.templatetags.tournament_extras import get_league_table

from .models import Prediction


def calculate_submission_total_points(submission):
    """Calculate total points for all predictions in a submission."""
    tournament = submission.tournament
    return sum(
        calculate_prediction_points(prediction, tournament=tournament) for prediction in submission.predictions.all()
    )


def calculate_submission_predictions_counts(submission):
    """Return tuple of (correct_predictions, played_predictions) for submission."""
    predictions = 0
    correct_predictions = 0
    for prediction in submission.predictions.all():
        if prediction.match.is_played:
            predictions += 1
            if is_prediction_correct(prediction):
                correct_predictions += 1
    return correct_predictions, predictions


def calculate_prediction_points(prediction, tournament=None):
    """Calculate points for a single prediction based on tournament settings."""
    if not prediction.match.is_played:
        return 0

    if not is_prediction_result_supported(prediction):
        return 0

    tournament = tournament or prediction.submission.tournament
    is_correct = is_prediction_correct(prediction)

    points = Decimal('0.00')
    if is_correct:
        if prediction.predicted_result == Prediction.Result.DRAW:
            points = tournament.points_for_draw_prediction
        else:
            points = tournament.points_for_win_prediction

    if prediction.is_special:
        if is_correct:
            points += tournament.special_match_points_delta
        else:
            points -= tournament.special_match_points_delta

    return points


def _match_result_to_prediction_result(match_result):
    if match_result in [MatchResult.HOME_WIN, MatchResult.HOME_DEF_WIN]:
        return Prediction.Result.HOME_WIN
    if match_result in [MatchResult.AWAY_WIN, MatchResult.AWAY_DEF_WIN]:
        return Prediction.Result.AWAY_WIN
    if match_result == MatchResult.DRAW:
        return Prediction.Result.DRAW
    return None


def is_prediction_correct(prediction: Prediction):
    """Return True when prediction exactly matches an already played match result."""
    if not prediction.match.is_played:
        return False

    prediction_result = _match_result_to_prediction_result(prediction.match.result.value)
    if prediction_result is None:
        return False

    return prediction.predicted_result == prediction_result


def is_prediction_result_supported(prediction):
    if not prediction.match.is_played:
        return False
    return _match_result_to_prediction_result(prediction.match.result.value) is not None


def get_teams_actual_positions(league):
    """Return mapping {team_id: actual_position} using current league table."""
    stages = list(league.stages.all())
    stage = stages[0] if stages else None
    table = get_league_table(league, stage)
    has_played_matches = any(row[1] > 0 for row in table)
    if not has_played_matches:
        return {}
    return {row[0].id: idx + 1 for idx, row in enumerate(table)}


def calculate_preseason_submission_points(submission, actual_positions, teams_count):
    """Calculate total preseason points for one submission using N - |actual - predicted|."""
    total_points = 0
    exact_hits = 0
    near_hits = 0
    items = []
    for item in submission.items.all().order_by('position'):
        actual_position = actual_positions.get(item.team_id)
        if actual_position is None:
            continue

        delta = abs(actual_position - item.position)
        points = teams_count - delta
        total_points += points
        if delta == 0:
            exact_hits += 1
        if delta <= 1:
            near_hits += 1
        items.append(
            {
                'team': item.team,
                'predicted_position': item.position,
                'actual_position': actual_position,
                'delta': delta,
                'points': points,
            }
        )

    return total_points, exact_hits, near_hits, items
