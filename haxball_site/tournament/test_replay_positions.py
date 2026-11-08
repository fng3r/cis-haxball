import copy
from pathlib import Path

from django.test import SimpleTestCase

from tournament.local_replay_analyzer import analyze_local_replay
from tournament.management.commands.audit_replay_positions import cohort, compare_games, summarize
from tournament.services.replay_positions import player_position_fields, select_positions
from tournament.services.replay_stats import _position_label, _position_sort_order


class ReplayPositionComparisonTests(SimpleTestCase):
    def setUp(self):
        self.legacy = [
            {
                'scoreRed': 1,
                'scoreBlue': 0,
                'gameTicks': 1800,
                'players': [{'nick': 'keeper', 'team': 'red', 'metrics': {'position': 'GK', 'playedTicks': 1800}}],
            }
        ]
        self.game = {
            'id': 7,
            'scoreRed': 1,
            'scoreBlue': 0,
            'gameTicks': 1800,
            'stadium': {'name': 'test'},
            'players': [
                {
                    'nick': 'keeper',
                    'team': 'red',
                    'playedTicks': 1800,
                    'primaryPosition': 'GK',
                    'primaryPositionConfidence': 0.9,
                    'positionRoles': [{'position': 'GK', 'ticks': 1800, 'share': 1}],
                }
            ],
        }

    def test_matches_identity_independently_of_display_order(self):
        rows, skipped = compare_games(self.legacy, {'games': [self.game]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['game_id'], 7)
        self.assertEqual(skipped, [])

    def test_rejects_ambiguous_games_and_players_instead_of_inflating_agreement(self):
        rows, skipped = compare_games(self.legacy, {'games': [self.game, {**self.game, 'id': 8}]})
        self.assertEqual(rows, [])
        self.assertEqual(skipped[0]['reason'], 'ambiguous_or_incompatible_game')
        self.game['players'] *= 2
        rows, skipped = compare_games(self.legacy, {'games': [self.game]})
        self.assertEqual(rows, [])
        self.assertEqual(skipped[0]['reason'], 'ambiguous_player_identity')

    def test_requires_same_replay_side(self):
        self.game['players'][0]['team'] = 'blue'
        rows, skipped = compare_games(self.legacy, {'games': [self.game]})
        self.assertEqual(rows, [])
        self.assertEqual(len(skipped), 1)

    def test_reports_explicit_primary_and_secondary_fields(self):
        self.game['players'][0].update(
            primaryPosition='DM',
            secondaryPosition='GK',
            primaryPositionConfidence=0.6,
            secondaryPositionConfidence=0.3,
        )
        rows, skipped = compare_games(self.legacy, {'games': [self.game]})
        self.assertEqual(skipped, [])
        self.assertEqual(rows[0]['position'], 'DM')
        self.assertEqual(rows[0]['primary_position'], 'DM')
        self.assertEqual(rows[0]['secondary_position'], 'GK')
        self.assertEqual(rows[0]['confidence'], 0.6)
        self.assertEqual(rows[0]['secondary_confidence'], 0.3)

    def test_keeps_unknowns_in_the_comparison_denominator(self):
        result = summarize(
            [
                {'position': 'ST', 'legacy_position': 'AM'},
                {'position': 'GK', 'legacy_position': 'GK'},
                {'position': None, 'legacy_position': 'DM'},
            ]
        )
        self.assertEqual(result['players'], 3)
        self.assertEqual(result['classified'], 2)
        self.assertEqual(result['exact_agreement'], 1)
        self.assertEqual(result['role_family_agreement'], 2)

    def test_validation_split_is_stable_and_disjoint(self):
        values = [cohort(i) for i in range(1, 101)]
        self.assertEqual(values, [cohort(i) for i in range(1, 101)])
        self.assertIn('validation', values)
        self.assertIn('calibration', values)


class EnginePositionContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.results = [
            analyze_local_replay((Path(__file__).parents[2] / f'analyzer/tests/fixtures/{name}').read_bytes())
            for name in ('futsal-multi.hbr2', 'cis5.hbr2')
        ]

    def test_production_cli_and_django_selection_agree_on_real_games(self):
        for result in self.results:
            self.assertEqual(result['positionVersion'], 4)
            for game in result['games']:
                for player in game['players']:
                    with self.subTest(game=game['id'], player=player['id']):
                        fields = player_position_fields(player)
                        selection = select_positions(fields['position_roles'], fields['position_observed_ticks'])
                        self.assertEqual(selection['primary_position'], player['primaryPosition'])
                        self.assertEqual(selection['secondary_position'], player['secondaryPosition'])
                        self.assertEqual(selection['primary_position_confidence'], player['primaryPositionConfidence'])
                        self.assertEqual(
                            selection['secondary_position_confidence'], player['secondaryPositionConfidence']
                        )

    def test_pre_position_cached_results_are_unavailable(self):
        fields = player_position_fields({'playedTicks': 28800, 'position': 'GK'})
        self.assertIsNone(fields['primary_position'])
        self.assertIsNone(fields['primary_position_confidence'])
        self.assertIsNone(fields['position_observed_ticks'])
        self.assertEqual(fields['position_roles'], [])

    def test_incomplete_earlier_role_exports_remain_unavailable(self):
        player = copy.deepcopy(self.results[0]['games'][0]['players'][0])
        player.pop('positionObservedTicks')
        for role in player['positionRoles']:
            role.pop('confidenceTicks')
        fields = player_position_fields(player)
        self.assertIsNone(fields['primary_position'])
        self.assertIsNone(fields['position_observed_ticks'])
        self.assertEqual(fields['position_roles'], [])

    def test_rejects_invalid_and_overcounted_role_evidence(self):
        for mutation in ('position', 'time', 'confidence', 'duplicate'):
            player = copy.deepcopy(self.results[0]['games'][0]['players'][0])
            if mutation == 'position':
                player['primaryPosition'] = 'UNKNOWN'
            elif mutation == 'time':
                player['positionRoles'][0]['ticks'] = player['playedTicks'] + 1
            elif mutation == 'confidence':
                player['positionRoles'][0]['confidenceTicks'] = float('nan')
            else:
                player['positionRoles'].append(copy.deepcopy(player['positionRoles'][0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                player_position_fields(player)

    def test_selection_uses_actual_role_time_and_unclassified_time(self):
        roles = [
            {'position': 'ST', 'ticks': 3600, 'confidenceTicks': 2880},
            {'position': 'DM', 'ticks': 1200, 'confidenceTicks': 960},
        ]
        self.assertEqual(select_positions(roles, 4800)['secondary_position'], 'DM')
        self.assertIsNone(select_positions(roles, 6000)['secondary_position'])
        self.assertIsNone(select_positions([{'position': 'GK', 'ticks': 899}], 899)['primary_position'])

    def test_selection_ties_match_engine_and_short_role_is_not_secondary(self):
        roles = [
            {'position': 'ST', 'ticks': 1800, 'confidenceTicks': 1260},
            {'position': 'DM', 'ticks': 1800, 'confidenceTicks': 1440},
        ]
        self.assertEqual(select_positions(roles, 3600)['primary_position'], 'DM')
        roles[0]['confidenceTicks'] = 1440
        self.assertEqual(select_positions(roles, 3600)['primary_position'], 'ST')
        roles[1]['ticks'] = 840
        roles[1]['confidenceTicks'] = 672
        self.assertIsNone(select_positions(roles, 2640)['secondary_position'])

    def test_legacy_labels_and_order_are_retained_for_all_supported_roles(self):
        self.assertEqual(
            [_position_label(p) for p in ('GK', 'DM', 'AM', 'LW', 'RW', 'ST', None)],
            ['ГК', 'ОП', 'НАП', 'НАП', 'НАП', 'НАП', None],
        )
        self.assertEqual(
            [_position_sort_order(p) for p in ('GK', 'DM', 'AM', 'LW', 'RW', 'ST', None)], [0, 1, 2, 2, 2, 2, 3]
        )

    def test_materialized_role_order_retains_first_observation_for_match_ties(self):
        player = {
            'playedTicks': 4800,
            'positionObservedTicks': 4800,
            'primaryPosition': 'GK',
            'secondaryPosition': 'ST',
            'primaryPositionConfidence': 0.5,
            'secondaryPositionConfidence': 0.3,
            'positionRoles': [
                {'position': 'GK', 'ticks': 3000, 'confidenceTicks': 2400},
                {'position': 'ST', 'ticks': 1800, 'confidenceTicks': 1440},
            ],
            'positionPeriods': [{'position': 'ST'}, {'position': 'GK'}],
        }
        fields = player_position_fields(player)
        self.assertEqual([role['position'] for role in fields['position_roles']], ['ST', 'GK'])
        self.assertEqual(select_positions(fields['position_roles'], 4800)['primary_position'], 'GK')
        # Later ST play makes total time and confidence equal: the first role wins.
        fields['position_roles'][0]['ticks'] += 1200
        fields['position_roles'][0]['confidenceTicks'] += 960
        self.assertEqual(select_positions(fields['position_roles'], 6000)['primary_position'], 'ST')
