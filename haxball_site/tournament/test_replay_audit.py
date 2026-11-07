import copy
from datetime import timedelta

from django.test import SimpleTestCase, TestCase

from .management.commands.audit_replay_games import (
    audit_match,
    needs_review,
    protocol_players,
    render_report,
    review_notes,
)
from .models import League, Match, Player, RegularStage, Season, Substitution, Team, TourNumber
from .services.replay_audit import evaluate_match, roster_evidence


class ReplayRelevanceTests(SimpleTestCase):
    def setUp(self):
        self.protocol = {'home': set(range(1, 5)), 'away': set(range(5, 9))}
        self.aliases = {f'p{i}': {i} for i in range(1, 17)}

    def game(self, seconds=480, goals=(), **metadata):
        return {
            'raw': {
                'gameTicks': seconds * 60,
                'scoreRed': sum(team == 'red' for _, team in goals),
                'scoreBlue': sum(team == 'blue' for _, team in goals),
                'goals': [{'gameTick': second * 60, 'team': team} for second, team in goals],
                'players': [
                    {'nick': f'p{i}', 'team': 'red' if i <= 4 else 'blue', 'playedTicks': max(seconds * 60, 1)}
                    for i in range(1, 9)
                ],
            },
            **metadata,
        }

    def evaluate(self, games, **options):
        return evaluate_match(games, self.protocol, self.aliases, **options)

    def test_full_halves_and_scored_warmup(self):
        report = self.evaluate([self.game(), self.game(143, [(50, 'red'), (90, 'blue')]), self.game()])
        self.assertEqual([g['recommendation'] for g in report['games']], ['retain', 'exclude', 'retain'])
        self.assertEqual(report['window_score'], [0, 0])

    def test_seven_plus_one_minute_continuation_including_scoreless_fragment(self):
        report = self.evaluate(
            [
                self.game(420, recording_number=1),
                self.game(60, recording_number=2),
                self.game(recording_number=2),
            ]
        )
        self.assertEqual([g['role'] for g in report['games'][:2]], ['possible_continuation'] * 2)
        self.assertFalse(any(g['recommendation'] == 'exclude' for g in report['games']))

    def test_scoreless_short_fragment_is_not_discarded_when_half_missing(self):
        report = self.evaluate([self.game(), self.game(30)])
        self.assertEqual(report['games'][1]['recommendation'], 'review')
        self.assertIn('regulation_coverage_uncertain', report['issues'])

    def test_golden_goal_after_two_regulation_halves_is_retained_for_review(self):
        report = self.evaluate([self.game(), self.game(), self.game(12, [(10, 'red')])], playoff=True)
        self.assertEqual(report['games'][2]['role'], 'overtime_candidate')
        self.assertEqual(report['games'][2]['recommendation'], 'review')

    def test_multiple_fixed_time_overtimes_are_not_excluded(self):
        report = self.evaluate([self.game() for _ in range(5)], playoff=True, duration_seconds=2400)
        self.assertEqual(report['games'][-1]['role'], 'overtime_candidate')
        self.assertNotIn('recorded_time_short_of_match_duration', report['issues'])

    def test_regular_match_extra_full_game_is_ambiguous_not_silently_dropped(self):
        report = self.evaluate([self.game(), self.game(), self.game()])
        self.assertEqual(report['games'][2]['recommendation'], 'review')
        self.assertIn('more_than_two_full_regulation_candidates', report['issues'])

    def test_trailing_native_overtime_is_not_junk_and_goals_after_eight_are_ignored(self):
        report = self.evaluate([self.game(540, [(480, 'red'), (481, 'blue')]), self.game()])
        self.assertEqual(report['games'][0]['recommendation'], 'retain')
        self.assertEqual(report['games'][0]['after_eight_minute_goals'], 1)
        self.assertEqual(report['window_score'], [1, 0])

    def test_total_roster_counts_late_joiners_and_substitutes_regardless_of_playtime(self):
        game = self.game()
        game['raw']['players'][-1]['playedTicks'] = 1
        game['raw']['players'].append({'nick': 'p9', 'team': 'red', 'playedTicks': 1})
        evidence = roster_evidence(game['raw'], self.protocol, self.aliases)
        self.assertEqual(evidence['sides']['red']['total'], 5)
        self.assertFalse(evidence['incomplete'])

    def test_incomplete_total_roster_is_strong_evidence_but_missing_half_is_flagged(self):
        game = self.game()
        game['raw']['players'].pop()
        report = self.evaluate([game, self.game()])
        self.assertEqual(report['games'][0]['recommendation'], 'exclude')
        self.assertIn('fewer_than_two_plausible_games', report['issues'])
        self.assertIn('full_length_game_with_strong_roster_problem', report['issues'])

    def test_renames_reconnects_and_spectators_do_not_inflate_roster(self):
        self.aliases['old nickname'] = {8}
        game = self.game()
        game['raw']['players'] += [
            {'nick': ' OLD NICKNAME ', 'team': 'blue', 'playedTicks': 10},
            {'nick': 'spectator', 'team': 'blue', 'playedTicks': 0},
        ]
        self.assertEqual(roster_evidence(game['raw'], self.protocol, self.aliases)['sides']['blue']['total'], 4)

    def test_known_outsiders_are_stronger_than_unknown_aliases(self):
        game = self.game()
        for i, p in enumerate(game['raw']['players'], 9):
            p['nick'] = f'p{i}'
        self.assertTrue(roster_evidence(game['raw'], self.protocol, self.aliases)['major_mismatch'])
        for i, p in enumerate(game['raw']['players']):
            p['nick'] = f'unresolved{i}'
        report = self.evaluate([game, self.game()])
        self.assertFalse(report['games'][0]['roster']['major_mismatch'])
        self.assertNotEqual(report['games'][0]['recommendation'], 'exclude')
        self.assertIn('mostly_unresolved_nicknames', report['games'][0]['reasons'])

    def test_missing_protocol_does_not_establish_mismatch(self):
        game = self.game()
        evidence = roster_evidence(game['raw'], {'home': set(), 'away': set()}, self.aliases)
        self.assertFalse(evidence['major_mismatch'])

    def test_single_outsider_does_not_invalidate_match(self):
        game = self.game()
        game['raw']['players'][0]['nick'] = 'p9'
        self.assertFalse(roster_evidence(game['raw'], self.protocol, self.aliases)['major_mismatch'])

    def test_different_opponent_is_strong_evidence_even_when_one_team_matches(self):
        game = self.game()
        for i, p in enumerate(game['raw']['players'][4:], 9):
            p['nick'] = f'p{i}'
        self.assertTrue(roster_evidence(game['raw'], self.protocol, self.aliases)['major_mismatch'])

    def test_side_swaps_and_persisted_override_affect_diagnostic_score(self):
        game = self.game(goals=[(20, 'red')])
        for p in game['raw']['players']:
            p['team'] = 'red' if p['team'] == 'blue' else 'blue'
        self.assertEqual(self.evaluate([game, self.game()])['window_score'], [0, 1])
        game['red_is_home_override'] = True
        self.assertEqual(self.evaluate([game, self.game()])['window_score'], [1, 0])

    def test_ambiguous_historical_nickname_is_not_identified_outsider(self):
        self.aliases['p1'] = {1, 15}
        evidence = roster_evidence(self.game()['raw'], self.protocol, self.aliases)
        self.assertEqual(evidence['unknown'], 1)

    def test_conflicting_side_evidence_keeps_home_red_default_and_requests_review(self):
        game = self.game()
        for p in game['raw']['players'][1:]:
            p['team'] = 'red' if p['team'] == 'blue' else 'blue'
        evidence = roster_evidence(game['raw'], self.protocol, self.aliases)
        self.assertEqual(evidence['mapping'], 'conflict')
        self.assertTrue(evidence['red_is_home'])

    def test_balanced_extra_goals_request_fair_play_review_without_exclusion(self):
        match = {
            'issues': ['score_difference_review_only'],
            'window_score': [6, 3],
            'official_score': [5, 2],
            'games': [],
        }
        self.assertIn('fair-play', ' '.join(review_notes(match)))

    def test_pure_evaluation_preserves_inputs_and_saved_decisions(self):
        games = [self.game(saved_included=False), self.game()]
        before = copy.deepcopy(games)
        self.evaluate(games)
        self.assertEqual(games, before)

    def test_already_excluded_restart_does_not_need_another_review(self):
        report = self.evaluate(
            [self.game(saved_included=True), self.game(5, saved_included=False), self.game(saved_included=True)]
        )
        self.assertFalse(needs_review(report))
        report['games'][1]['saved_included'] = True
        self.assertTrue(needs_review(report))

    def test_report_table_is_not_broken_by_player_roster_notes(self):
        games = [
            self.game(
                saved_included=True,
                recording_number=1,
                game_id=0,
                part_id=1,
                source_url='https://example.org',
                label='First | half',
            )
        ]
        result = self.evaluate(games)
        match = {
            'match_id': 1,
            'url': '/match/1',
            'teams': ['A', 'B'],
            'league': 'League',
            'tour': '1',
            'official_score': [0, 0],
            'duration_seconds': 960,
            'recording_count': 1,
            **result,
        }
        report = render_report({'season': 'Test', 'generated_at': 'now', 'heuristic': 'test', 'matches': [match]})
        self.assertIn('First \\| half', report)
        self.assertIn('regulation_coverage_uncertain', report)


class ReplayAuditProtocolTests(TestCase):
    def test_protocol_includes_substitutes_and_technical_result_is_exempt(self):
        season = Season.objects.create(
            title='Audit', short_title='Audit', number=99, is_active=False, type='russian_championship'
        )
        league = League.objects.create(title='Audit', slug='audit', championship=season)
        stage = RegularStage.objects.create(league=league, order=1, type='REG')
        tour = TourNumber.objects.create(league=league, stage=stage, number=1)
        home = Team.objects.create(title='Home', slug='audit-home')
        away = Team.objects.create(title='Away', slug='audit-away')
        match = Match.objects.create(
            league=league,
            stage=stage,
            numb_tour=tour,
            team_home=home,
            team_guest=away,
            is_played=True,
            duration=timedelta(minutes=16),
        )
        starter = Player.objects.create(nickname='Starter')
        substitute = Player.objects.create(nickname='Substitute')
        Substitution.objects.create(
            match=match, team=home, player_out=starter, player_in=substitute, time_min=4, time_sec=0
        )
        self.assertEqual(protocol_players(match)['home'], {starter.pk, substitute.pk})
        result = match.result
        result.value, result.set_manually = 'HDW', True
        result.save()
        match.refresh_from_db()
        audit = audit_match(match, {}, 4)
        self.assertTrue(audit['technical_result'])
        self.assertEqual(audit['issues'], [])
