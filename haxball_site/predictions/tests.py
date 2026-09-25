from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from tournament.models import MatchResult

from .models import (
    MatchPredictionOutcome,
    Prediction,
    PredictionsContestTournament,
    PredictionSubmission,
    format_handicap_value,
    format_total_value,
)
from .points_service import (
    calculate_avg_coefficient,
    calculate_prediction_points,
    calculate_roi,
    calculate_submission_predictions_counts,
    get_prediction_coefficient,
    is_prediction_correct,
    is_prediction_void,
)
from .utils import build_match_offers_map, build_match_outcome_groups_map, build_match_outcomes_map


def make_outcome_match(*, score_home, score_guest, result_value, is_played=True):
    return SimpleNamespace(
        is_played=is_played,
        score_home=score_home,
        score_guest=score_guest,
        result=SimpleNamespace(value=result_value),
    )


def make_outcome(*, market, selection, line=None, coefficient='2.00'):
    return MatchPredictionOutcome(
        market=market,
        selection=selection,
        line=Decimal(line) if line is not None else None,
        coefficient=Decimal(coefficient),
    )


def make_outcome_prediction(outcome, match):
    return SimpleNamespace(
        match=match,
        outcome=outcome,
        outcome_id=1,
        predicted_result=None,
        is_special=False,
    )


def make_coefficient_tournament(nominal='100'):
    return SimpleNamespace(
        nominal_points=Decimal(nominal),
        scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS,
    )


class FormatValuesTest(SimpleTestCase):
    def test_format_handicap_value(self):
        self.assertEqual(format_handicap_value('-5.50'), '-5.5')
        self.assertEqual(format_handicap_value('5.50'), '+5.5')
        self.assertEqual(format_handicap_value('0.00'), '0')

    def test_format_total_value(self):
        self.assertEqual(format_total_value('5.50'), '5.5')
        self.assertEqual(format_total_value('5.00'), '5')

    def test_outcome_display_label(self):
        self.assertEqual(make_outcome(market='RESULT', selection='HW').display_label, 'П1')
        self.assertEqual(make_outcome(market='HANDICAP', selection='F1', line='-1.5').display_label, 'Ф1 (-1.5)')
        self.assertEqual(make_outcome(market='TOTAL', selection='OVER', line='5.5').display_label, 'ТБ (5.5)')
        self.assertEqual(make_outcome(market='TOTAL', selection='UNDER', line='5.0').display_label, 'ТМ (5)')
        self.assertEqual(make_outcome(market='ITOTAL', selection='HT_OVER', line='1.5').display_label, 'ИТБ1 (1.5)')
        self.assertEqual(make_outcome(market='ITOTAL', selection='AT_UNDER', line='2').display_label, 'ИТМ2 (2)')


class OutcomeSettleTest(SimpleTestCase):
    def test_result_market(self):
        match = make_outcome_match(score_home=3, score_guest=1, result_value=MatchResult.HOME_WIN)
        self.assertTrue(make_outcome(market='RESULT', selection='HW').settle(match))
        self.assertTrue(make_outcome(market='RESULT', selection='HWD').settle(match))
        self.assertFalse(make_outcome(market='RESULT', selection='D').settle(match))
        self.assertFalse(make_outcome(market='RESULT', selection='AW').settle(match))

    def test_result_draw_covers_double_chances(self):
        match = make_outcome_match(score_home=1, score_guest=1, result_value=MatchResult.DRAW)
        self.assertTrue(make_outcome(market='RESULT', selection='D').settle(match))
        self.assertTrue(make_outcome(market='RESULT', selection='HWD').settle(match))
        self.assertTrue(make_outcome(market='RESULT', selection='AWD').settle(match))
        self.assertFalse(make_outcome(market='RESULT', selection='HW').settle(match))

    def test_handicap_market(self):
        match = make_outcome_match(score_home=4, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertTrue(make_outcome(market='HANDICAP', selection='F1', line='-1.5').settle(match))
        self.assertFalse(make_outcome(market='HANDICAP', selection='F1', line='-2.5').settle(match))

    def test_total_market(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertTrue(make_outcome(market='TOTAL', selection='OVER', line='4.5').settle(match))
        self.assertFalse(make_outcome(market='TOTAL', selection='UNDER', line='4.5').settle(match))
        self.assertTrue(make_outcome(market='TOTAL', selection='UNDER', line='5.5').settle(match))

    def test_total_push_is_void(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertIsNone(make_outcome(market='TOTAL', selection='OVER', line='5').settle(match))
        self.assertIsNone(make_outcome(market='TOTAL', selection='UNDER', line='5').settle(match))

    def test_individual_total_home(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertTrue(make_outcome(market='ITOTAL', selection='HT_OVER', line='2.5').settle(match))
        self.assertFalse(make_outcome(market='ITOTAL', selection='HT_UNDER', line='2.5').settle(match))
        self.assertFalse(make_outcome(market='ITOTAL', selection='HT_OVER', line='3.5').settle(match))

    def test_individual_total_away(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertTrue(make_outcome(market='ITOTAL', selection='AT_UNDER', line='2.5').settle(match))
        self.assertFalse(make_outcome(market='ITOTAL', selection='AT_OVER', line='2.5').settle(match))

    def test_individual_total_push_is_void(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        self.assertIsNone(make_outcome(market='ITOTAL', selection='HT_OVER', line='3').settle(match))
        self.assertIsNone(make_outcome(market='ITOTAL', selection='AT_UNDER', line='2').settle(match))

    def test_tech_defeat_voids_every_market(self):
        for result_value in (
            MatchResult.HOME_DEF_WIN,
            MatchResult.AWAY_DEF_WIN,
            MatchResult.MUTUAL_TECH_DEFEAT,
        ):
            match = make_outcome_match(score_home=5, score_guest=0, result_value=result_value)
            self.assertIsNone(make_outcome(market='RESULT', selection='HW').settle(match))
            self.assertIsNone(make_outcome(market='HANDICAP', selection='F1', line='-1.5').settle(match))
            self.assertIsNone(make_outcome(market='TOTAL', selection='OVER', line='0.5').settle(match))
            self.assertIsNone(make_outcome(market='ITOTAL', selection='HT_OVER', line='0.5').settle(match))

    def test_unplayed_match_is_void(self):
        match = make_outcome_match(score_home=3, score_guest=0, result_value=MatchResult.HOME_WIN, is_played=False)
        self.assertIsNone(make_outcome(market='RESULT', selection='HW').settle(match))


class OutcomePointsTest(SimpleTestCase):
    def test_correct_outcome_scores_net_win(self):
        tournament = make_coefficient_tournament()
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        prediction = make_outcome_prediction(
            make_outcome(market='TOTAL', selection='OVER', line='4.5', coefficient='3.40'), match
        )
        self.assertEqual(calculate_prediction_points(prediction, tournament=tournament), Decimal('240.00'))
        self.assertTrue(is_prediction_correct(prediction))
        self.assertFalse(is_prediction_void(prediction))

    def test_wrong_outcome_scores_minus_nominal(self):
        tournament = make_coefficient_tournament()
        match = make_outcome_match(score_home=1, score_guest=0, result_value=MatchResult.HOME_WIN)
        prediction = make_outcome_prediction(
            make_outcome(market='TOTAL', selection='OVER', line='4.5', coefficient='3.40'), match
        )
        self.assertEqual(calculate_prediction_points(prediction, tournament=tournament), Decimal('-100'))
        self.assertFalse(is_prediction_correct(prediction))

    def test_push_scores_zero_and_void(self):
        tournament = make_coefficient_tournament()
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        prediction = make_outcome_prediction(
            make_outcome(market='TOTAL', selection='OVER', line='5', coefficient='1.90'), match
        )
        self.assertEqual(calculate_prediction_points(prediction, tournament=tournament), Decimal('0.00'))
        self.assertTrue(is_prediction_void(prediction))
        self.assertFalse(is_prediction_correct(prediction))

    def test_missing_outcome_scores_zero(self):
        tournament = make_coefficient_tournament()
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        prediction = SimpleNamespace(
            match=match, outcome=None, outcome_id=None, predicted_result='HW', is_special=False
        )
        self.assertEqual(calculate_prediction_points(prediction, tournament=tournament), Decimal('0.00'))

    def test_unplayed_match_scores_zero(self):
        tournament = make_coefficient_tournament()
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN, is_played=False)
        prediction = make_outcome_prediction(make_outcome(market='RESULT', selection='HW', coefficient='2.00'), match)
        self.assertEqual(calculate_prediction_points(prediction, tournament=tournament), 0)

    def test_get_prediction_coefficient(self):
        match = make_outcome_match(score_home=3, score_guest=0, result_value=MatchResult.HOME_WIN)
        prediction = make_outcome_prediction(make_outcome(market='RESULT', selection='HW', coefficient='4.75'), match)
        self.assertEqual(get_prediction_coefficient(prediction), Decimal('4.75'))


class ClassicPointsTest(SimpleTestCase):
    def make_classic_prediction(self, predicted_result, result_value, is_special=False):
        match = SimpleNamespace(
            is_played=True,
            score_home=2,
            score_guest=1,
            result=SimpleNamespace(value=result_value),
        )
        return SimpleNamespace(
            match=match,
            outcome=None,
            outcome_id=None,
            predicted_result=predicted_result,
            is_special=is_special,
        )

    def make_tournament(self):
        return SimpleNamespace(
            nominal_points=Decimal('100'),
            scoring_method=PredictionsContestTournament.ScoringMethod.CLASSIC,
            points_for_win_prediction=Decimal('1'),
            points_for_draw_prediction=Decimal('3'),
            special_match_points_delta=Decimal('0.5'),
        )

    def test_correct_win_scores_win_points(self):
        prediction = self.make_classic_prediction('HW', MatchResult.HOME_WIN)
        self.assertEqual(calculate_prediction_points(prediction, tournament=self.make_tournament()), Decimal('1'))
        self.assertTrue(is_prediction_correct(prediction))

    def test_correct_draw_scores_draw_points(self):
        match = SimpleNamespace(
            is_played=True,
            score_home=1,
            score_guest=1,
            result=SimpleNamespace(value=MatchResult.DRAW),
        )
        prediction = SimpleNamespace(match=match, outcome=None, outcome_id=None, predicted_result='D', is_special=False)
        self.assertEqual(calculate_prediction_points(prediction, tournament=self.make_tournament()), Decimal('3'))

    def test_wrong_prediction_scores_zero(self):
        prediction = self.make_classic_prediction('AW', MatchResult.HOME_WIN)
        self.assertEqual(calculate_prediction_points(prediction, tournament=self.make_tournament()), Decimal('0.00'))
        self.assertFalse(is_prediction_correct(prediction))

    def test_special_adds_delta(self):
        prediction = self.make_classic_prediction('HW', MatchResult.HOME_WIN, is_special=True)
        self.assertEqual(calculate_prediction_points(prediction, tournament=self.make_tournament()), Decimal('1.50'))

    def test_special_miss_subtracts_delta(self):
        prediction = self.make_classic_prediction('AW', MatchResult.HOME_WIN, is_special=True)
        self.assertEqual(calculate_prediction_points(prediction, tournament=self.make_tournament()), Decimal('-0.50'))


class VoidExcludedFromCountsTest(SimpleTestCase):
    def test_void_prediction_not_counted(self):
        match = make_outcome_match(score_home=3, score_guest=2, result_value=MatchResult.HOME_WIN)
        void_pred = make_outcome_prediction(
            make_outcome(market='TOTAL', selection='OVER', line='5', coefficient='1.90'), match
        )
        win_pred = make_outcome_prediction(
            make_outcome(market='TOTAL', selection='OVER', line='4.5', coefficient='1.90'), match
        )
        submission = SimpleNamespace(
            predictions=SimpleNamespace(all=lambda: [void_pred, win_pred]),
        )
        self.assertEqual(calculate_submission_predictions_counts(submission), (1, 1))


class RoiAndAvgCoefficientTest(SimpleTestCase):
    def test_roi(self):
        # +140 profit over 2 staked nominals of 100 => +70%.
        self.assertEqual(calculate_roi(Decimal('140'), Decimal('100'), 2), Decimal('70'))
        self.assertEqual(calculate_roi(Decimal('-100'), Decimal('100'), 2), Decimal('-50'))
        self.assertEqual(calculate_roi(Decimal('0'), Decimal('100'), 3), Decimal('0'))

    def test_roi_no_played_is_none(self):
        self.assertIsNone(calculate_roi(Decimal('0'), Decimal('100'), 0))

    def test_avg_coefficient(self):
        self.assertEqual(calculate_avg_coefficient(Decimal('5.60'), 2), Decimal('2.80'))

    def test_avg_coefficient_no_data_is_none(self):
        self.assertIsNone(calculate_avg_coefficient(Decimal('0'), 0))


class BuildMatchOutcomesMapTest(SimpleTestCase):
    def test_maps_outcomes_by_match_grouped_by_market(self):
        result = make_outcome(market='RESULT', selection='HW')
        handicap = make_outcome(market='HANDICAP', selection='F1', line='-1.5')
        total = make_outcome(market='TOTAL', selection='OVER', line='5.5')
        itotal = make_outcome(market='ITOTAL', selection='HT_OVER', line='1.5')
        tour = SimpleNamespace(
            tour_matches=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=1,
                        prediction_offer=SimpleNamespace(
                            is_published=True,
                            outcomes=SimpleNamespace(all=lambda: [itotal, total, handicap, result]),
                        ),
                    ),
                    SimpleNamespace(id=2, prediction_offer=None),
                    SimpleNamespace(
                        id=3,
                        prediction_offer=SimpleNamespace(
                            is_published=False,
                            outcomes=SimpleNamespace(all=lambda: [result]),
                        ),
                    ),
                ]
            )
        )
        result_map = build_match_outcomes_map(tour)
        self.assertEqual(result_map[1], [result, handicap, total, itotal])
        self.assertNotIn(2, result_map)
        self.assertNotIn(3, result_map)

    def test_groups_by_market_in_canonical_order(self):
        result = make_outcome(market='RESULT', selection='HW')
        itotal = make_outcome(market='ITOTAL', selection='HT_OVER', line='1.5')
        handicap = make_outcome(market='HANDICAP', selection='F1', line='-1.5')
        tour = SimpleNamespace(
            tour_matches=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=1,
                        prediction_offer=SimpleNamespace(
                            is_published=True,
                            outcomes=SimpleNamespace(all=lambda: [itotal, handicap, result]),
                        ),
                    ),
                ]
            )
        )
        groups = build_match_outcome_groups_map(tour)
        self.assertEqual(list(groups[1].keys()), ['RESULT', 'HANDICAP', 'ITOTAL'])

    def test_build_offers_map(self):
        offer = SimpleNamespace(is_published=True)
        tour = SimpleNamespace(
            tour_matches=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(id=1, prediction_offer=offer),
                    SimpleNamespace(id=2, prediction_offer=None),
                ]
            )
        )
        self.assertEqual(build_match_offers_map(tour), {1: offer})


def make_clean_prediction(*, scoring_method, predicted_result=None, outcome=None, is_special=False):
    """Build an unsaved Prediction with stubbed submission chain. No DB required."""
    tournament = PredictionsContestTournament(scoring_method=scoring_method)
    submission = PredictionSubmission(user_id=1, tour_id=1, tournament=tournament)
    return Prediction(
        submission=submission,
        match_id=1,
        predicted_result=predicted_result,
        outcome=outcome,
        is_special=is_special,
    )


class PredictionCleanTest(SimpleTestCase):
    def test_classic_valid(self):
        make_clean_prediction(
            scoring_method=PredictionsContestTournament.ScoringMethod.CLASSIC, predicted_result='HW'
        ).clean()

    def test_classic_requires_predicted_result(self):
        with self.assertRaises(ValidationError):
            make_clean_prediction(scoring_method=PredictionsContestTournament.ScoringMethod.CLASSIC).clean()

    def test_classic_rejects_outcome(self):
        outcome = MatchPredictionOutcome(market='RESULT', selection='HW', coefficient='2.00')
        with self.assertRaises(ValidationError):
            make_clean_prediction(
                scoring_method=PredictionsContestTournament.ScoringMethod.CLASSIC,
                predicted_result='HW',
                outcome=outcome,
            ).clean()

    def test_classic_rejects_double_chance(self):
        with self.assertRaises(ValidationError):
            make_clean_prediction(
                scoring_method=PredictionsContestTournament.ScoringMethod.CLASSIC, predicted_result='HWD'
            ).clean()

    def test_coefficients_valid(self):
        outcome = MatchPredictionOutcome(market='TOTAL', selection='OVER', line='4.5', coefficient='2.00')
        make_clean_prediction(
            scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS, outcome=outcome
        ).clean()

    def test_coefficients_requires_outcome(self):
        with self.assertRaises(ValidationError):
            make_clean_prediction(
                scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS,
                predicted_result='HW',
            ).clean()

    def test_coefficients_rejects_classic_columns(self):
        outcome = MatchPredictionOutcome(market='RESULT', selection='HW', coefficient='2.00')
        with self.assertRaises(ValidationError):
            make_clean_prediction(
                scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS,
                outcome=outcome,
                predicted_result='HW',
            ).clean()

    def test_coefficients_rejects_special(self):
        outcome = MatchPredictionOutcome(market='RESULT', selection='HW', coefficient='2.00')
        with self.assertRaises(ValidationError):
            make_clean_prediction(
                scoring_method=PredictionsContestTournament.ScoringMethod.COEFFICIENTS,
                outcome=outcome,
                is_special=True,
            ).clean()
