from decimal import Decimal

from tournament.models import MatchResult
from tournament.templatetags.tournament_extras import get_league_table

from .models import MatchPredictionCoefficients, MatchPredictionHandicap, Prediction, PredictionsContestTournament


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

    if tournament.scoring_method == PredictionsContestTournament.ScoringMethod.COEFFICIENT:
        if prediction.handicap_id:
            return _calculate_handicap_prediction_points(prediction, tournament)

        return _calculate_coefficient_prediction_points(prediction, tournament)

    return _calculate_legacy_prediction_points(prediction, tournament)


def _calculate_handicap_prediction_points(prediction, tournament):
    """Betting-style points for a handicap outcome.

    Correct: nominal * (coefficient - 1). Incorrect: -nominal.
    """
    if is_handicap_correct(prediction):
        return tournament.nominal_points * (prediction.handicap.coefficient - 1)
    return -tournament.nominal_points


def _calculate_coefficient_prediction_points(prediction, tournament):
    """Betting-style points for a coefficient outcome.

    Correct: nominal * (coefficient - 1). Incorrect: -nominal.
    Returns 0 when no coefficient is set for the predicted outcome.
    """
    coefficient = get_prediction_coefficient(prediction)
    if coefficient is None:
        return Decimal('0.00')

    if is_prediction_correct(prediction):
        return tournament.nominal_points * (coefficient - 1)
    return -tournament.nominal_points


def _calculate_legacy_prediction_points(prediction, tournament):
    """Points for legacy format (fixed win/draw points and special bonus/penalty)."""
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


def get_prediction_coefficient(prediction) -> Decimal | None:
    """Return the coefficient of the prediction's outcome, or None if not set."""
    if prediction.handicap_id:
        return prediction.handicap.coefficient

    coefficients = getattr(prediction.match, 'prediction_coefficients', None)
    if coefficients is None:
        coefficients = MatchPredictionCoefficients.objects.filter(match=prediction.match).first()
    if coefficients is None:
        return None
    return coefficients.coefficient_for(prediction.predicted_result)


def _match_result_to_prediction_results(match_result):
    """Return the set of prediction outcomes satisfied by a match result."""
    if match_result in [MatchResult.HOME_WIN, MatchResult.HOME_DEF_WIN]:
        return {Prediction.Result.HOME_WIN, Prediction.Result.HOME_WIN_OR_DRAW}
    if match_result in [MatchResult.AWAY_WIN, MatchResult.AWAY_DEF_WIN]:
        return {Prediction.Result.AWAY_WIN, Prediction.Result.AWAY_WIN_OR_DRAW}
    if match_result == MatchResult.DRAW:
        return {Prediction.Result.DRAW, Prediction.Result.HOME_WIN_OR_DRAW, Prediction.Result.AWAY_WIN_OR_DRAW}
    return set()


def is_handicap_correct(prediction: Prediction):
    """Return True when a handicap prediction wins: team's score with the handicap applied beats the opponent."""
    match = prediction.match
    if not match.is_played:
        return False

    handicap = prediction.handicap
    home_score = Decimal(match.score_home)
    away_score = Decimal(match.score_guest)

    if handicap.team == MatchPredictionHandicap.Team.HOME:
        return home_score + handicap.value > away_score
    return away_score + handicap.value > home_score


def is_prediction_correct(prediction: Prediction):
    """Return True when the prediction's outcome matches an already played match result."""
    if not prediction.match.is_played:
        return False

    if prediction.handicap_id:
        return is_handicap_correct(prediction)

    satisfied_results = _match_result_to_prediction_results(prediction.match.result.value)
    if not satisfied_results:
        return False

    return prediction.predicted_result in satisfied_results


def is_prediction_result_supported(prediction):
    if not prediction.match.is_played:
        return False
    return bool(_match_result_to_prediction_results(prediction.match.result.value))


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
