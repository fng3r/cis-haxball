from django.test import SimpleTestCase

from tournament.management.commands.audit_replay_positions import cohort, compare_games, summarize


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
                    'position': 'GK',
                    'positionConfidence': 0.9,
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
