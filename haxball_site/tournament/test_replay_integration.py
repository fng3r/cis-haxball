import copy
import hashlib
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .local_replay_analyzer import analyze_local_replay
from .models import (
    League,
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
    Player,
    RegularStage,
    ReplayGame,
    ReplayMatchPart,
    ReplayPlayerStats,
    ReplayRecording,
    ReplayTeamStats,
    Season,
    Team,
    TourNumber,
)
from .services.local_replays import (
    active_parts,
    analyzer_link,
    classify_parts,
    infer_mapping,
    ingest_match,
    materialize,
    reconcile_parts,
)
from .services.replay_positions import select_positions
from .services.replay_presentation import statistics
from .services.replay_stats import MatchReplayStatsAggregator
from .services.replay_storage import recording_bytes
from .tasks import fetch_match_replay_stats, reanalyze_replay_recordings


class LocalReplayIntegrationTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        storage = override_settings(MEDIA_ROOT=self.media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.client = Client(HTTP_USER_AGENT='Replay integration tests')

    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(
            title='ЧР, 17 сезон', short_title='ЧР #17', number=25, is_active=True, type='russian_championship'
        )
        cls.league = League.objects.create(title='League', slug='test', championship=cls.season)
        cls.stage = RegularStage.objects.create(league=cls.league, order=1, type='REG')
        cls.tour = TourNumber.objects.create(league=cls.league, stage=cls.stage, number=1)
        cls.home = Team.objects.create(title='Home', short_title='H', slug='home')
        cls.away = Team.objects.create(title='Away', short_title='A', slug='away')
        cls.url = 'https://replay.thehax.pl/test-recording'
        cls.match = Match.objects.create(
            league=cls.league,
            stage=cls.stage,
            numb_tour=cls.tour,
            team_home=cls.home,
            team_guest=cls.away,
            replays=[cls.url],
        )
        cls.result = analyze_local_replay(
            (Path(__file__).parents[2] / 'analyzer/tests/fixtures/futsal-multi.hbr2').read_bytes()
        )

    def seed(self, result=None):
        result = copy.deepcopy(result or self.result)
        recording = ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:test-recording',
            replay_url=self.url,
            raw_response=result,
            status='ready',
        )
        materialize(recording, result, {'home': set(), 'away': set()}, {})
        self.match.replay_parts.update(included=True)
        reconcile_parts(self.match)
        return recording

    def regulation_with_restart(self):
        """Two full 4v4 halves with a scored extra game; all metrics remain in raw/domain storage."""
        result = copy.deepcopy(self.result)
        template = result['games'][0]
        result['games'] = [copy.deepcopy(template) for _ in range(3)]
        for index, game in enumerate(result['games']):
            game.update(id=index, gameTicks=28800 if index != 1 else 8614, scoreRed=0, scoreBlue=0, goals=[])
            player_template = {
                key: value
                for key, value in game['players'][0].items()
                if not key.startswith(('position', 'primaryPosition', 'secondaryPosition'))
            }
            game['players'] = [
                {
                    **copy.deepcopy(player_template),
                    'id': f'{n}:{side}',
                    'nick': f'{side}-{n}',
                    'team': side,
                    'playedTicks': game['gameTicks'],
                }
                for side in ('red', 'blue')
                for n in range(4)
            ]
        result['games'][1].update(scoreRed=1, kicks=[1000, 1000])
        return result

    def test_ingestion_classifies_scored_restart_and_keeps_raw_and_domain_statistics(self):
        raw = self.regulation_with_restart()
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'recording'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=raw),
        ):
            ingest_match(self.match.pk)
        parts = active_parts(self.match)
        self.assertEqual([p.included for p in parts], [True, False, True])
        self.assertEqual([p.label for p in parts if p.included], ['1 тайм', '2 тайм'])
        self.assertIn('двух полных таймов', parts[1].exclusion_reason)
        self.assertFalse(parts[1].auto_included)
        self.assertIsNone(parts[1].included_override)
        self.assertEqual(ReplayRecording.objects.get(match=self.match).raw_response, raw)
        self.assertEqual(parts[1].game.team_stats.get(side='red').kicks, 1000)
        self.assertEqual(parts[1].game.player_stats.count(), 8)
        self.assertEqual(len(statistics(self.match)['parts_summary']), 2)
        before = [(p.pk, p.included, p.exclusion_reason, p.label) for p in parts]
        with patch('tournament.services.local_replays.analyze_local_replay') as engine:
            ingest_match(self.match.pk)
            engine.assert_not_called()
        self.assertEqual([(p.pk, p.included, p.exclusion_reason, p.label) for p in active_parts(self.match)], before)

    def test_cached_parts_are_reclassified_when_other_recordings_are_added_or_removed(self):
        raw = self.regulation_with_restart()
        short = {**copy.deepcopy(raw), 'games': [raw['games'][1]]}
        self.seed(short)
        classify_parts(self.match)
        part = active_parts(self.match)[0]
        self.assertTrue(part.included)  # Not enough context to call it a restart yet.
        other_url = 'https://replay.thehax.pl/second-recording'
        self.match.replays = [self.url, other_url]
        self.match.save(update_fields=['replays'])
        full = {**copy.deepcopy(raw), 'games': [raw['games'][0], raw['games'][2]]}
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'full'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=full),
        ):
            ingest_match(self.match.pk)
        part.refresh_from_db()
        self.assertFalse(part.included)
        self.match.replays = [self.url]
        self.match.save(update_fields=['replays'])
        ingest_match(self.match.pk)
        part.refresh_from_db()
        self.assertTrue(part.included)
        self.assertEqual(part.exclusion_reason, '')

    def test_reclassification_preserves_manual_exclusion_and_manual_inclusion(self):
        self.seed(self.regulation_with_restart())
        classify_parts(self.match)
        parts = active_parts(self.match)
        parts[0].included = False
        parts[0].save(update_fields=['included'])
        parts[1].included = True
        parts[1].save(update_fields=['included'])
        ingest_match(self.match.pk)
        parts = active_parts(self.match)
        self.assertFalse(parts[0].included_override)
        self.assertEqual(parts[0].exclusion_reason, 'Исключена вручную.')
        self.assertTrue(parts[1].included_override)
        self.assertTrue(parts[1].included)
        self.assertEqual(parts[1].exclusion_reason, '')

    def test_legacy_current_part_decisions_bootstrap_against_previous_filter(self):
        raw = self.regulation_with_restart()
        raw['games'][1].update(gameTicks=10, scoreRed=0, scoreBlue=0)
        self.seed(raw)
        self.match.replay_parts.update(auto_included=None)
        # Formerly excluded short scoreless game was explicitly included by an editor.
        classify_parts(self.match)
        part = self.match.replay_parts.get(game__engine_game_id=1)
        self.assertTrue(part.included_override)
        self.assertTrue(part.included)
        # Ordinary previously-included scored warmup adopts the new evaluator.
        raw['games'][1].update(gameTicks=8614, scoreRed=1)
        ReplayRecording.objects.filter(match=self.match).update(raw_response=raw)
        ReplayMatchPart.objects.filter(pk=part.pk).update(auto_included=None, included_override=None)
        classify_parts(self.match)
        part.refresh_from_db()
        self.assertFalse(part.included)
        self.assertIsNone(part.included_override)

    def test_manually_excluded_full_game_cannot_make_other_game_a_restart(self):
        self.seed(self.regulation_with_restart())
        part = self.match.replay_parts.get(game__engine_game_id=0)
        part.included_override = False
        part.save(update_fields=['included_override'])
        classify_parts(self.match)
        short = self.match.replay_parts.get(game__engine_game_id=1)
        self.assertTrue(short.included)
        self.assertEqual(short.exclusion_reason, '')

    def test_admin_manual_override_can_be_cleared_to_restore_automatic_decision(self):
        self.seed(self.regulation_with_restart())
        classify_parts(self.match)
        part = self.match.replay_parts.get(game__engine_game_id=1)
        editor = User.objects.create_superuser('inclusion-editor', password='test')
        self.client.force_login(editor)
        endpoint = reverse('admin:tournament_replaymatchpart_change', args=[part.pk])
        self.assertEqual(
            self.client.post(
                endpoint,
                {
                    'included': 'on',
                    'included_override': 'True',
                    'red_is_home_override': '',
                    '_save': 'Save',
                },
            ).status_code,
            302,
        )
        part.refresh_from_db()
        self.assertTrue(part.included)
        ingest_match(self.match.pk)
        part.refresh_from_db()
        self.assertTrue(part.included)
        self.assertEqual(
            self.client.post(
                endpoint,
                {
                    'included': 'on',
                    'included_override': '',
                    'red_is_home_override': '',
                    '_save': 'Save',
                },
            ).status_code,
            302,
        )
        part.refresh_from_db()
        self.assertFalse(part.included)
        self.assertIsNone(part.included_override)
        self.assertIn('двух полных таймов', part.exclusion_reason)

    def test_normalized_storage_and_legacy_preservation(self):
        legacy = MatchReplay.objects.create(
            match=self.match,
            replay_url=self.url,
            raw_stats_json=[{'old': 'unchanged'}],
            analyzer_replay_id='old',
            status='ready',
        )
        part = MatchReplayStats.objects.create(match=self.match, match_replay=legacy, score_red=8)
        MatchReplayStatsPlayer.objects.create(replay_stats=part, nick='old player', rating=9.8, played_ticks=10)
        before = [list(model.objects.values()) for model in (MatchReplay, MatchReplayStats, MatchReplayStatsPlayer)]
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result) as engine,
        ):
            self.assertEqual(fetch_match_replay_stats(self.match.pk)['created_games'], 2)
            ids = list(ReplayMatchPart.objects.values_list('pk', flat=True))
            self.assertEqual(fetch_match_replay_stats(self.match.pk)['created_games'], 0)
            self.assertEqual(engine.call_count, 1)
        self.assertEqual(list(ReplayMatchPart.objects.values_list('pk', flat=True)), ids)
        self.assertEqual(ReplayGame.objects.count(), 2)
        self.assertEqual(ReplayTeamStats.objects.count(), 4)
        self.assertEqual(ReplayPlayerStats.objects.count(), sum(len(g['players']) for g in self.result['games']))
        self.assertEqual(
            before, [list(model.objects.values()) for model in (MatchReplay, MatchReplayStats, MatchReplayStatsPlayer)]
        )

    def test_same_bytes_changed_output_refreshes_metrics_and_preserves_corrections(self):
        recording = self.seed()
        part = self.match.replay_parts.order_by('pk').first()
        part.included = False
        part.label_override = 'Исправленный тайм'
        part.order_override = 42
        part.red_is_home_override = False
        part.save()
        raw = copy.deepcopy(self.result)
        raw['games'][0]['kicks'][0] += 17
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            ingest_match(self.match.pk, force=True)
        recording.refresh_from_db()
        first_hash = recording.content_sha256
        response_hash = recording.response_sha256
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=raw) as engine,
        ):
            ingest_match(self.match.pk, force=True)
            engine.assert_called_once()
        recording.refresh_from_db()
        part.refresh_from_db()
        self.assertEqual(recording.content_sha256, first_hash)
        self.assertNotEqual(recording.response_sha256, response_hash)
        self.assertEqual(recording.raw_response, raw)
        self.assertEqual(part.game.team_stats.get(side='red').kicks, raw['games'][0]['kicks'][0])
        self.assertFalse(part.included)
        self.assertEqual(part.label, 'Исправленный тайм')
        self.assertEqual(part.order, 42)
        self.assertFalse(part.red_is_home)

    def test_game_identity_is_engine_id_not_array_position_or_start_tick(self):
        recording = self.seed()
        ids = {p.game.engine_game_id: p.pk for p in active_parts(self.match)}
        raw = copy.deepcopy(self.result)
        raw['games'].reverse()
        raw['games'][0]['startTick'] += 123
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        self.assertEqual({p.game.engine_game_id: p.pk for p in active_parts(self.match)}, ids)

    def test_real_engine_positions_are_persisted_and_use_legacy_badges_and_order(self):
        self.seed()
        for game in self.result['games']:
            for player in game['players']:
                stored = ReplayPlayerStats.objects.get(
                    game__engine_game_id=game['id'], nick=player['nick'], side=player['team']
                )
                self.assertEqual(stored.primary_position, player['primaryPosition'])
                self.assertEqual(stored.avatar, player['avatar'])
                self.assertEqual(stored.secondary_position, player['secondaryPosition'])
                self.assertEqual(stored.primary_position_confidence, player['primaryPositionConfidence'])
                self.assertEqual(stored.position_observed_ticks, player['positionObservedTicks'])
                self.assertEqual(
                    sum(role['ticks'] for role in stored.position_roles),
                    sum(role['ticks'] for role in player['positionRoles']),
                )
        stats = statistics(self.match)
        html = render_to_string('tournament/match/players_stats.html', {'agg': stats})
        self.assertIn('Поз.', html)
        for label in ('ГК', 'ОП', 'НАП'):
            self.assertIn(f'>{label}</span>', html)
        for role in ('GK', 'DM', 'AM', 'ST'):
            self.assertNotIn(f'>{role}</span>', html)
        order = {'ГК': 0, 'ОП': 1, 'НАП': 2, None: 3}
        for team in (self.home, self.away):
            labels = [row['position_label'] for row in stats['players'] if row['team_obj'] == team]
            self.assertEqual(labels, sorted(labels, key=lambda label: order[label]))

    @staticmethod
    def position_player(template, *, identity, nick, side, seconds_by_role):
        roles = [
            {'position': role, 'ticks': seconds * 60, 'confidenceTicks': seconds * 60 * 0.8}
            for role, seconds in seconds_by_role
        ]
        observed = sum(role['ticks'] for role in roles)
        selected = select_positions(roles, observed)
        return {
            **copy.deepcopy(template),
            'id': identity,
            'nick': nick,
            'team': side,
            'playedTicks': observed,
            'primaryPosition': selected['primary_position'],
            'secondaryPosition': selected['secondary_position'],
            'primaryPositionConfidence': selected['primary_position_confidence'],
            'secondaryPositionConfidence': selected['secondary_position_confidence'],
            'positionObservedTicks': observed,
            'positionRoles': roles,
        }

    def test_match_roles_use_actual_role_time_resolve_identity_and_exclude_unselected_parts(self):
        raw = copy.deepcopy(self.result)
        template = raw['games'][0]['players'][0]
        raw['games'] = [copy.deepcopy(raw['games'][0]) for _ in range(3)]
        specifications = [
            ([('ST', 250), ('DM', 230)], 'red', 'first alias'),
            ([('DM', 240), ('ST', 60)], 'blue', 'second alias'),
            ([('GK', 1000)], 'red', 'excluded alias'),
        ]
        for index, (roles, side, nick) in enumerate(specifications):
            raw['games'][index]['id'] = index
            raw['games'][index]['players'] = [
                self.position_player(template, identity=f'{index}:{side}', nick=nick, side=side, seconds_by_role=roles)
            ]
        recording = self.seed(raw)
        player = Player.objects.create(nickname='Resolved player')
        recording.games.all().get(engine_game_id=0).player_stats.update(player=player)
        recording.games.all().get(engine_game_id=1).player_stats.update(player=player)
        recording.games.all().get(engine_game_id=2).player_stats.update(player=player)
        parts = active_parts(self.match)
        parts[1].red_is_home_override = False
        parts[1].save()
        parts[2].included = False
        parts[2].save()
        stats = statistics(self.match)
        self.assertEqual(len(stats['players']), 1)
        row = stats['players'][0]
        self.assertEqual(row['player'], player)
        self.assertEqual(row['team_obj'], self.home)
        self.assertEqual(row['position'], 'DM')  # 470s DM versus 310s ST, not entire-half labels.
        self.assertEqual(row['position_label'], 'ОП')
        self.assertEqual(row['played_ticks'], 780 * 60)
        self.assertEqual([part['players'][0]['position_label'] for part in stats['parts_players']], ['НАП', 'ОП'])

    def test_secondary_is_stored_but_never_rendered_in_player_table(self):
        raw = copy.deepcopy(self.result)
        raw['games'] = raw['games'][:1]
        raw['games'][0]['players'] = [
            self.position_player(
                raw['games'][0]['players'][0],
                identity='only:red',
                nick='Only player',
                side='red',
                seconds_by_role=[('GK', 300), ('DM', 180)],
            )
        ]
        self.seed(raw)
        stored = ReplayPlayerStats.objects.get()
        self.assertEqual(stored.primary_position, 'GK')
        self.assertEqual(stored.secondary_position, 'DM')
        stats = statistics(self.match)
        html = render_to_string('tournament/match/players_stats.html', {'agg': stats})
        self.assertIn('>ГК</span>', html)
        self.assertNotIn('>ОП</span>', html)
        self.assertNotIn('Дополнительная', html)
        self.assertNotIn('secondary_position', html)

    def test_reanalysis_updates_positions_without_recreating_parts_or_changing_overrides(self):
        recording = self.seed()
        part = active_parts(self.match)[0]
        part.label_override = 'Preserved'
        part.red_is_home_override = False
        part.save()
        row = part.game.player_stats.first()
        raw = copy.deepcopy(self.result)
        player = next(p for p in raw['games'][0]['players'] if p['nick'] == row.nick and p['team'] == row.side)
        updated = self.position_player(
            player,
            identity=player['id'],
            nick=player['nick'],
            side=player['team'],
            seconds_by_role=[('AM', 300), ('GK', 180)],
        )
        player.update(updated)
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=raw),
        ):
            ingest_match(self.match.pk, force=True)
        row.refresh_from_db()
        part.refresh_from_db()
        self.assertEqual(row.primary_position, 'AM')
        self.assertEqual(row.secondary_position, 'GK')
        self.assertEqual(part.label, 'Preserved')
        self.assertFalse(part.red_is_home)
        self.assertEqual(ReplayRecording.objects.get(pk=recording.pk).raw_response, raw)

    def test_old_cached_response_clears_unavailable_position_fields(self):
        recording = self.seed()
        raw = copy.deepcopy(self.result)
        for game in raw['games']:
            for player in game['players']:
                for key in list(player):
                    if key.startswith(('position', 'primaryPosition', 'secondaryPosition')):
                        player.pop(key)
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        self.assertFalse(ReplayPlayerStats.objects.exclude(primary_position=None).exists())
        self.assertFalse(ReplayPlayerStats.objects.exclude(position_observed_ticks=None).exists())
        self.assertTrue(all(row['position_label'] is None for row in statistics(self.match)['players']))

    def test_reanalysis_materializes_avatar_changes_clearing_and_missing_metadata(self):
        recording = self.seed()
        row = ReplayPlayerStats.objects.get(game__engine_game_id=0, nick='R3venGe-')
        self.assertEqual(row.avatar, 'R3')
        raw = copy.deepcopy(self.result)
        player = next(p for p in raw['games'][0]['players'] if p['nick'] == 'R3venGe-')
        player['avatar'] = '😀'
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        row.refresh_from_db()
        self.assertEqual(row.avatar, '😀')
        player['avatar'] = None
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        row.refresh_from_db()
        self.assertIsNone(row.avatar)
        player.pop('avatar')
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        row.refresh_from_db()
        self.assertIsNone(row.avatar)

    def test_legacy_primary_interpretation_and_short_historical_labels_are_unchanged(self):
        recording = MatchReplay.objects.create(match=self.match, replay_url=self.url, status='ready')
        part = MatchReplayStats.objects.create(match=self.match, match_replay=recording)
        for nick, position in [('attacker', 'AM'), ('keeper', 'GK'), ('defender', 'DM')]:
            MatchReplayStatsPlayer.objects.create(
                replay_stats=part, nick=nick, team=self.home, position=position, played_ticks=100
            )
        result = MatchReplayStatsAggregator(match=self.match, parts=[part]).build()
        self.assertEqual([p['position_label'] for p in result['players']], ['ГК', 'ОП', 'НАП'])
        self.assertEqual([p['nick'] for p in result['players']], ['keeper', 'defender', 'attacker'])
        html = render_to_string('tournament/match/players_stats.html', {'agg': result})
        self.assertIn('>ГК</span>', html)
        self.assertIn('>ОП</span>', html)
        self.assertIn('>НАП</span>', html)

    def test_disappeared_game_retains_editorial_record_and_returns_with_same_identity(self):
        recording = self.seed()
        part = active_parts(self.match)[1]
        part.label_override = 'Keep me'
        part.save()
        raw = copy.deepcopy(self.result)
        raw['games'] = raw['games'][:1]
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        part.refresh_from_db()
        self.assertFalse(part.game.available)
        self.assertTrue(statistics(self.match)['needs_review'])
        self.assertNotIn(part.pk, [p.pk for p in active_parts(self.match)])
        materialize(recording, self.result, {'home': set(), 'away': set()}, {})
        part.refresh_from_db()
        self.assertTrue(part.game.available)
        self.assertEqual(part.label, 'Keep me')

    def test_failed_reanalysis_does_not_publish_partial_metrics(self):
        recording = self.seed()
        before = list(ReplayTeamStats.objects.order_by('pk').values())
        invalid = copy.deepcopy(self.result)
        invalid['games'][1]['kicks'] = []
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=invalid),
        ):
            self.assertEqual(ingest_match(self.match.pk, force=True)['failed_recordings'], 1)
        recording.refresh_from_db()
        self.assertEqual(recording.raw_response, self.result)
        self.assertEqual(before, list(ReplayTeamStats.objects.order_by('pk').values()))
        self.assertTrue(statistics(self.match)['has_data'])

    def test_recognition_side_swaps_substitutions_and_default(self):
        roster = {'home': {'alice', 'sub'}, 'away': {'bob'}}
        players = [
            {'nick': 'Alice', 'team': 'red', 'playedTicks': 100},
            {'nick': 'sub', 'team': 'red', 'playedTicks': 5},
            {'nick': 'Bob', 'team': 'blue', 'playedTicks': 100},
        ]
        self.assertEqual(infer_mapping({'players': players}, roster), (True, 'roster'))
        swapped = [{**p, 'team': 'blue' if p['team'] == 'red' else 'red'} for p in players]
        self.assertEqual(infer_mapping({'players': swapped}, roster), (False, 'roster'))
        self.assertEqual(infer_mapping({'players': players + swapped}, roster), (True, 'conflict'))
        self.assertEqual(infer_mapping({'players': []}, roster), (True, 'default'))

    def test_removed_readded_and_alternate_urls_preserve_parts(self):
        self.seed()
        part = active_parts(self.match)[0]
        part.included = False
        part.save()
        self.match.replays = []
        self.assertEqual(active_parts(self.match), [])
        self.match.replays = [self.url + '/download']
        self.assertEqual(len(active_parts(self.match)), 2)
        self.assertFalse(active_parts(self.match)[0].included)
        Match.objects.filter(pk=self.match.pk).update(replays=[self.url + '/download', self.url])
        with patch('tournament.services.replay_storage.download_replay') as download:
            ingest_match(self.match.pk)
            download.assert_not_called()
        self.assertEqual(ReplayRecording.objects.count(), 1)

    def test_manifest_is_absolute_whole_match_read_only_and_cors_scoped(self):
        recording = self.seed()
        part = active_parts(self.match)[1]
        part.order_override = 0
        part.label_override = 'Custom'
        part.red_is_home_override = False
        part.save()
        endpoint = reverse('tournament:analyzer_manifest', args=[self.match.pk])
        response = self.client.get(endpoint, HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:3000')
        data = response.json()
        self.assertEqual(data['match']['season']['id'], self.season.pk)
        self.assertEqual(len(data['parts']), 2)
        self.assertEqual(data['parts'][1]['gameId'], part.game.engine_game_id)
        self.assertEqual(data['recordings'][0]['id'], recording.pk)
        self.assertTrue(data['recordings'][0]['url'].startswith('http://testserver/'))
        self.assertTrue(data['teams']['home']['logo'].startswith('http://testserver/'))
        self.assertNotIn('canMap', data)
        self.assertNotIn('mappingUrl', data['recordings'][0])
        self.assertEqual(self.client.post(endpoint).status_code, 405)
        self.assertNotIn('Access-Control-Allow-Origin', self.client.get(endpoint, HTTP_ORIGIN='https://untrusted.test'))
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2actual') as download:
            binary = self.client.get(data['recordings'][0]['url'], HTTP_ORIGIN='http://localhost:3000')
            self.assertEqual(binary.content, b'HBR2actual')
            self.assertEqual(binary['Access-Control-Allow-Origin'], 'http://localhost:3000')
            download.assert_called_once_with(self.url)
        self.assertIn('context=', analyzer_link(self.match))
        self.assertIn(f'part={part.pk}', analyzer_link(self.match, part=part))

    def test_existing_statistics_design_uses_only_included_domain_parts(self):
        self.seed()
        part = active_parts(self.match)[0]
        part.label_override = 'My half'
        part.red_is_home_override = False
        part.save()
        stats = statistics(self.match)
        self.assertEqual(stats['parts_summary'][0]['part_label'], 'My half')
        self.assertEqual(stats['parts_summary'][0]['score_home'], part.game.team_stats.get(side='blue').goals)
        self.assertIsNone(stats['players'][0]['shots_total'])
        expected_passes = sum(row.passes_completed for row in ReplayTeamStats.objects.all())
        self.assertEqual(stats['team']['passes_home'] + stats['team']['passes_guest'], expected_passes)
        html = render_to_string('tournament/match/replay_statistics_content.html', {'match': self.match, 'agg': stats})
        self.assertIn('Команды', html)
        self.assertIn('Игроки', html)
        self.assertIn('My half', html)
        self.assertNotIn('Командные итоги для игр', html)
        for unsupported in (
            'Передачи (%)',
            'Сейвы',
            'Рейтинг',
            "key: 'pass_accuracy'",
            "key: 'saves'",
            "key: 'rating'",
        ):
            self.assertNotIn(unsupported, html)
        self.assertIn('Поз.', html)
        part.included = False
        part.save()
        self.assertEqual(len(statistics(self.match)['parts_summary']), 1)

    def test_manual_reinclusion_survives_reclassification(self):
        raw = self.regulation_with_restart()
        raw['games'][1].update(gameTicks=1, scoreRed=0, scoreBlue=0)
        recording = ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:test-recording',
            replay_url=self.url,
            raw_response=raw,
            status='ready',
        )
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        classify_parts(self.match)
        part = ReplayMatchPart.objects.get(game__engine_game_id=raw['games'][1]['id'])
        self.assertFalse(part.included)
        part.included = True
        part.save()
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        classify_parts(self.match)
        part.refresh_from_db()
        self.assertTrue(part.included)
        self.assertTrue(part.included_override)
        self.assertEqual(part.exclusion_reason, '')

    def test_admin_groups_and_rare_corrections(self):
        self.seed()
        user = User.objects.create_superuser('editor', password='test')
        self.client.force_login(user)
        response = self.client.get(reverse('admin:app_list', args=['tournament']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Реплеи и статистика')
        self.assertContains(response, 'Реплеи — архивная статистика')
        part = active_parts(self.match)[0]
        endpoint = reverse('admin:tournament_replaymatchpart_change', args=[part.pk])
        response = self.client.post(
            endpoint,
            {
                'included': 'on',
                'order_override': '8',
                'label_override': 'Fixed',
                'red_is_home_override': 'False',
                '_save': 'Save',
            },
        )
        self.assertEqual(response.status_code, 302)
        part.refresh_from_db()
        self.assertEqual(part.label, 'Fixed')
        self.assertEqual(part.order, 8)
        self.assertFalse(part.red_is_home)

    def test_forced_command_queues_reanalysis_and_normal_command_reuses_results(self):
        with patch('tournament.tasks.fetch_match_replay_stats.delay') as queued:
            call_command('build_match_stats', match_ids=[self.match.pk], reanalyze=True, stdout=StringIO())
            queued.assert_called_once_with(self.match.pk, force=True)

    def test_reanalyze_all_queues_existing_recordings_once_per_match_including_removed_sources(self):
        current = self.seed()
        archived = ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:archived',
            replay_url='https://replay.thehax.pl/archived',
            status='failed',
        )
        other_match = Match.objects.create(
            league=self.league,
            stage=self.stage,
            numb_tour=self.tour,
            team_home=self.home,
            team_guest=self.away,
            replays=['https://replay.thehax.pl/not-stored'],
        )
        other = ReplayRecording.objects.create(
            match=other_match,
            source_key='powtorki:other',
            replay_url='https://replay.thehax.pl/other',
            status='pending',
        )
        output = StringIO()
        with (
            patch('tournament.tasks.reanalyze_replay_recordings.delay') as queued,
            patch('tournament.tasks.fetch_match_replay_stats.delay') as normal,
        ):
            call_command('build_match_stats', reanalyze_all=True, stdout=output)
            self.assertEqual([call.args[0] for call in queued.call_args_list], [[current.pk, archived.pk], [other.pk]])
            normal.assert_not_called()
        self.assertIn('Queued reanalysis for 3 recordings across 2 matches', output.getvalue())
        self.assertEqual(ReplayRecording.objects.count(), 3)

    def test_reanalyze_all_handles_empty_recording_store(self):
        output = StringIO()
        with patch('tournament.tasks.reanalyze_replay_recordings.delay') as queued:
            call_command('build_match_stats', reanalyze_all=True, stdout=output)
            queued.assert_not_called()
        self.assertIn('0 recordings across 0 matches', output.getvalue())

    def test_reanalyze_all_rejects_season_and_match_filters_before_queueing(self):
        for filters in ({'season': self.season.number}, {'match_ids': [self.match.pk]}):
            with (
                self.subTest(filters=filters),
                patch('tournament.tasks.reanalyze_replay_recordings.delay') as queued,
                self.assertRaises(CommandError),
            ):
                call_command('build_match_stats', reanalyze_all=True, stdout=StringIO(), **filters)
            queued.assert_not_called()

    def test_recording_task_does_not_reanalyze_the_same_match_multiple_times(self):
        current = self.seed()
        archived = ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:archived',
            replay_url='https://replay.thehax.pl/archived',
        )
        ids = [current.pk, archived.pk]
        with patch('tournament.services.local_replays.ingest_match', return_value={'ok': True}) as ingest:
            result = reanalyze_replay_recordings.run(ids)
        ingest.assert_called_once_with(self.match.pk, force=True, recording_ids=ids)
        self.assertEqual(result, [{'ok': True}])

    def test_selected_recording_reanalysis_does_not_create_unrelated_new_sources(self):
        current = self.seed()
        archived = ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:archived',
            replay_url='https://replay.thehax.pl/archived',
        )
        self.match.replays = [self.url, 'https://replay.thehax.pl/not-stored']
        self.match.save(update_fields=['replays'])
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture') as download,
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            result = reanalyze_replay_recordings.run([archived.pk])
        download.assert_called_once_with(archived.replay_url)
        self.assertEqual(result[0]['failed_recordings'], 0)
        self.assertEqual(ReplayRecording.objects.count(), 2)
        self.assertEqual(archived.games.count(), len(self.result['games']))
        current.refresh_from_db()
        self.assertIsNone(current.analyzed_at)
        self.assertTrue(all(part.game.recording_id == current.pk for part in active_parts(self.match)))

    def test_match_deletion_cascades_without_leaving_protected_part_dependencies(self):
        self.seed()
        self.match.delete()
        self.assertFalse(ReplayRecording.objects.exists())
        self.assertFalse(ReplayMatchPart.objects.exists())

    def test_legacy_statistics_keep_the_existing_source_and_metrics(self):

        from .services.replay_stats import MatchReplayStatsAggregator

        recording = MatchReplay.objects.create(match=self.match, replay_url=self.url, analyzer_replay_id='legacy-id')
        part = MatchReplayStats.objects.create(match=self.match, match_replay=recording, score_red=3)
        MatchReplayStatsPlayer.objects.create(replay_stats=part, nick='Legacy player', rating=8.5, played_ticks=3600)
        agg = MatchReplayStatsAggregator(self.match, [part]).build()
        html = render_to_string(
            'tournament/match/statistics.html',
            {
                'match': self.match,
                'selected_replay_stats': agg,
                'selected_replay_status': 'success',
            },
        )
        self.assertIn('https://replay.hax.ma', html)
        self.assertIn('Legacy player', html)
        self.assertIn('Рейтинг', html)

    def test_manifest_reports_unprepared_sources_without_silently_omitting_them(self):
        endpoint = reverse('tournament:analyzer_manifest', args=[self.match.pk])
        self.assertEqual(self.client.get(endpoint).status_code, 409)

    def test_existing_legacy_screen_remains_default_until_current_data_is_ready(self):
        from .models import MatchReplayStatsStatus

        recording = MatchReplay.objects.create(match=self.match, replay_url=self.url)
        part = MatchReplayStats.objects.create(match=self.match, match_replay=recording)
        MatchReplayStatsPlayer.objects.create(replay_stats=part, nick='Preserved legacy player', played_ticks=3600)
        MatchReplayStatsStatus.objects.create(match=self.match, status='success')
        ReplayRecording.objects.create(
            match=self.match,
            source_key='powtorki:test-recording',
            replay_url=self.url,
            status='failed',
            error_message='Node unavailable',
        )
        Match.objects.filter(pk=self.match.pk).update(is_played=True)
        response = self.client.get(reverse('tournament:match_detail', args=[self.match.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['show_current_replay_stats'])
        self.assertContains(response, 'Preserved legacy player')

    def test_manifest_context_titles_single_stage_and_duplicate_part_labels(self):
        self.seed()
        self.match.replay_parts.update(label_override='Тайм')
        endpoint = reverse('tournament:analyzer_manifest', args=[self.match.pk])
        data = self.client.get(endpoint).json()
        self.assertEqual(data['match']['league']['name'], self.league.title)
        self.assertEqual(data['teams']['home']['shortName'], self.home.short_title)
        self.assertEqual(data['teams']['away']['shortName'], self.away.short_title)
        self.assertIsNone(data['match']['stage'])
        self.assertEqual(data['match']['tour']['name'], '1 тур')
        self.assertEqual([p['displayLabel'] for p in data['parts']], ['Тайм [1]', 'Тайм [2]'])
        self.assertEqual([p['label'] for p in data['parts']], ['Тайм', 'Тайм'])
        from .models import PlayOffStage

        PlayOffStage.objects.create(league=self.league, order=2)
        data = self.client.get(endpoint).json()
        self.assertEqual(data['match']['stage']['name'], str(self.stage))
        first = active_parts(self.match)[0]
        first.included = False
        first.save()
        data = self.client.get(endpoint).json()
        self.assertEqual([p['displayLabel'] for p in data['parts']], ['Тайм', 'Тайм'])

    def test_manifest_playoff_round_names_and_explicit_tour_name(self):
        from .models import PlayOffStage

        self.seed()
        stage = PlayOffStage.objects.create(league=self.league, order=2)
        final_tour = TourNumber.objects.create(league=self.league, stage=stage, number=2)
        semifinal = TourNumber.objects.create(league=self.league, stage=stage, number=1)
        Match.objects.filter(pk=self.match.pk).update(stage=stage, numb_tour=semifinal)
        endpoint = reverse('tournament:analyzer_manifest', args=[self.match.pk])
        self.assertEqual(self.client.get(endpoint).json()['match']['tour']['name'], '1/2 Финала')
        Match.objects.filter(pk=self.match.pk).update(numb_tour=final_tour)
        self.assertEqual(self.client.get(endpoint).json()['match']['tour']['name'], 'Финал')
        TourNumber.objects.filter(pk=final_tour.pk).update(name='Grand Final')
        self.assertEqual(self.client.get(endpoint).json()['match']['tour']['name'], 'Grand Final')

    def test_manifest_series_match_number_follows_match_page_order(self):
        from datetime import date

        from .models import MatchSeries, PlayOffStage

        self.seed()
        stage = PlayOffStage.objects.create(league=self.league, order=2)
        tour = TourNumber.objects.create(league=self.league, stage=stage, number=1)
        series = MatchSeries.objects.create(tour=tour, bracket_slot=1, team_home=self.home, team_guest=self.away)
        Match.objects.filter(pk=self.match.pk).update(
            stage=stage, numb_tour=tour, series=series, match_date=date(2026, 10, 2)
        )
        endpoint = reverse('tournament:analyzer_manifest', args=[self.match.pk])
        self.assertIsNone(self.client.get(endpoint).json()['match']['series'])
        second = Match.objects.create(
            league=self.league,
            stage=stage,
            numb_tour=tour,
            series=series,
            team_home=self.away,
            team_guest=self.home,
            match_date=date(2026, 10, 1),
        )
        data = self.client.get(endpoint).json()
        self.assertEqual(data['match']['series'], {'id': series.pk, 'matchNumber': 1})
        self.assertEqual(data['match']['tour']['name'], 'Финал')
        Match.objects.filter(pk=second.pk).update(replays=[self.url])
        record = ReplayRecording.objects.create(match=second, source_key='powtorki:test-recording', replay_url=self.url)
        materialize(record, self.result, {'home': set(), 'away': set()}, {})
        data = self.client.get(reverse('tournament:analyzer_manifest', args=[second.pk])).json()
        self.assertEqual(data['match']['series']['matchNumber'], 2)
        Match.objects.filter(pk=self.match.pk).update(series=None)
        self.assertIsNone(self.client.get(endpoint).json()['match']['series'])
        self.assertIsNone(
            self.client.get(reverse('tournament:analyzer_manifest', args=[second.pk])).json()['match']['series']
        )

    def test_replay_admin_models_are_deletable_and_parent_deletion_cascades(self):
        from django.contrib import admin
        from django.test import RequestFactory

        self.seed()
        user = User.objects.create_superuser('delete-editor', password='test')
        self.client.force_login(user)
        request = RequestFactory().get('/')
        request.user = user
        for model in (ReplayRecording, ReplayGame, ReplayMatchPart, ReplayTeamStats, ReplayPlayerStats):
            model_admin = admin.site._registry[model]
            self.assertTrue(model_admin.has_delete_permission(request))
            self.assertIn('delete_selected', model_admin.get_actions(request))
        game = ReplayGame.objects.first()
        part_id = game.match_part.pk
        endpoint = reverse('admin:tournament_replaygame_delete', args=[game.pk])
        self.assertEqual(self.client.post(endpoint, {'post': 'yes'}).status_code, 302)
        self.assertFalse(ReplayMatchPart.objects.filter(pk=part_id).exists())
        self.assertFalse(ReplayTeamStats.objects.filter(game_id=game.pk).exists())
        recording = ReplayRecording.objects.first()
        endpoint = reverse('admin:tournament_replayrecording_delete', args=[recording.pk])
        self.assertEqual(self.client.post(endpoint, {'post': 'yes'}).status_code, 302)
        self.assertFalse(ReplayGame.objects.exists())
        self.assertFalse(ReplayMatchPart.objects.exists())
        self.assertFalse(ReplayPlayerStats.objects.exists())

    def test_match_part_changelist_saves_all_overrides_and_inclusion(self):
        self.seed()
        editor = User.objects.create_superuser('list-editor', password='test')
        self.client.force_login(editor)
        endpoint = reverse('admin:tournament_replaymatchpart_changelist')
        response = self.client.get(endpoint)
        formset = response.context['cl'].formset
        data = {f'{formset.prefix}-{key}': value for key, value in formset.management_form.initial.items()}
        target_id = None
        for index, form in enumerate(formset.forms):
            part = form.instance
            prefix = f'{formset.prefix}-{index}-'
            data[prefix + 'id'] = part.pk
            data[prefix + 'order_override'] = ''
            data[prefix + 'label_override'] = ''
            data[prefix + 'red_is_home_override'] = '1'
            if index == 0:
                target_id = part.pk
                data[prefix + 'order_override'] = '7'
                data[prefix + 'label_override'] = 'List correction'
                data[prefix + 'red_is_home_override'] = '3'
            else:
                data[prefix + 'included'] = 'on'
        data['_save'] = 'Save'
        response = self.client.post(endpoint, data)
        self.assertEqual(response.status_code, 302)
        part = ReplayMatchPart.objects.get(pk=target_id)
        self.assertFalse(part.included)
        self.assertEqual(part.order, 7)
        self.assertEqual(part.label, 'List correction')
        self.assertFalse(part.red_is_home)

    def test_exclusion_omits_all_team_player_and_comparison_statistics(self):
        self.seed()
        self.match.replay_parts.update(included=False)
        payload = statistics(self.match)
        self.assertFalse(payload['has_data'])
        self.assertEqual(payload['team']['score_home'], 0)
        self.assertEqual(payload['team']['passes_home'], 0)
        self.assertEqual(payload['team']['duration_label'], '00:00')
        self.assertEqual(payload['players'], [])
        self.assertEqual(payload['parts_players'], [])
        self.assertEqual(payload['players_comparison_data']['total'], {'home': [], 'guest': []})
        self.assertEqual(payload['players_comparison_data']['parts'], [])
        self.assertEqual(ReplayGame.objects.count(), len(self.result['games']))
        self.assertTrue(ReplayPlayerStats.objects.exists())

    def test_deleted_team_stats_do_not_break_the_match_statistics_page(self):
        self.seed()
        part = active_parts(self.match)[0]
        part.game.team_stats.filter(side='red').delete()
        payload = statistics(self.match)
        self.assertTrue(payload['needs_review'])
        self.assertEqual(len(payload['parts_summary']), 1)

    def test_current_statistics_take_precedence_even_with_legacy_query_parameter(self):
        from .models import MatchReplayStatsStatus

        self.seed()
        old = MatchReplay.objects.create(match=self.match, replay_url=self.url)
        MatchReplayStats.objects.create(match=self.match, match_replay=old, score_red=99)
        MatchReplayStatsStatus.objects.create(match=self.match, status='success')
        Match.objects.filter(pk=self.match.pk).update(is_played=True)
        endpoint = reverse('tournament:match_detail', args=[self.match.pk])
        for query in ('', '?stats=legacy', '?stats=current'):
            response = self.client.get(endpoint + query)
            self.assertTrue(response.context['show_current_replay_stats'])
            self.assertEqual(response.context['selected_replay_status'], 'success')
            self.assertTrue(response.context['selected_replay_stats']['is_current'])

    def test_current_statuses_use_existing_failure_pending_and_partial_ui(self):
        record = ReplayRecording.objects.create(
            match=self.match, source_key='powtorki:test-recording', replay_url=self.url
        )
        endpoint = reverse('tournament:match_detail', args=[self.match.pk])
        Match.objects.filter(pk=self.match.pk).update(is_played=True)
        response = self.client.get(endpoint)
        self.assertEqual(response.context['selected_replay_status'], 'pending')
        self.assertContains(response, 'Реплей обрабатывается.')
        record.status = 'failed'
        record.save()
        response = self.client.get(endpoint)
        self.assertEqual(response.context['selected_replay_status'], 'failed')
        self.assertContains(response, 'Статистика для данного матча недоступна')
        materialize(record, self.result, {'home': set(), 'away': set()}, {})
        self.match.replay_parts.update(included=True)
        response = self.client.get(endpoint)
        self.assertEqual(response.context['selected_replay_status'], 'partial')
        self.assertContains(response, 'Статистика загружена частично.')
        self.assertNotContains(response, 'Не удалось обновить одну из записей')
        self.assertNotContains(response, 'Нет выбранных частей с доступной статистикой')

    def test_generated_overtime_parts_use_bracketed_duplicate_labels_in_both_apps(self):
        raw = copy.deepcopy(self.result)
        for game_id in (2, 3, 4):
            raw['games'].append({**copy.deepcopy(raw['games'][0]), 'id': game_id})
        self.seed(raw)
        self.assertEqual(
            [part.label for part in active_parts(self.match)],
            ['1 тайм', '2 тайм', 'Доп. время [1]', 'Доп. время [2]', 'Доп. время [3]'],
        )
        expected = ['1 тайм', '2 тайм', 'Доп. время [1]', 'Доп. время [2]', 'Доп. время [3]']
        self.assertEqual([part['part_label'] for part in statistics(self.match)['parts_summary']], expected)
        data = self.client.get(reverse('tournament:analyzer_manifest', args=[self.match.pk])).json()
        self.assertEqual([part['displayLabel'] for part in data['parts']], expected)
        last = active_parts(self.match)[-1]
        last.label_override = 'Custom overtime'
        last.save()
        reconcile_parts(self.match)
        last.refresh_from_db()
        self.assertEqual(last.label, 'Custom overtime')

    def test_archive_is_reused_by_playback_and_forced_reanalysis(self):
        recording = self.seed()
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive') as download:
            self.assertEqual(recording_bytes(recording), b'HBR2archive')
            download.assert_called_once_with(self.url)
        recording.refresh_from_db()
        self.assertTrue(recording.replay_file.storage.exists(recording.replay_file.name))
        with (
            patch(
                'tournament.services.replay_storage.download_replay', side_effect=RuntimeError('offline')
            ) as download,
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result) as engine,
        ):
            response = self.client.get(reverse('tournament:analyzer_recording', args=[self.match.pk, recording.pk]))
            self.assertEqual(response.content, b'HBR2archive')
            self.assertEqual(ingest_match(self.match.pk, force=True)['failed_recordings'], 0)
            engine.assert_called_once_with(b'HBR2archive')
            download.assert_not_called()

    def test_analysis_failure_retains_download_for_retry(self):
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive'),
            patch('tournament.services.local_replays.analyze_local_replay', side_effect=ValueError('engine failed')),
        ):
            self.assertEqual(ingest_match(self.match.pk)['failed_recordings'], 1)
        recording = ReplayRecording.objects.get(match=self.match)
        self.assertEqual(recording.status, 'failed')
        self.assertTrue(recording.replay_file)
        with (
            patch('tournament.services.replay_storage.download_replay') as download,
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            self.assertEqual(ingest_match(self.match.pk)['failed_recordings'], 0)
            download.assert_not_called()

    def test_archive_backfill_preserves_analysis_and_rejects_changed_bytes(self):
        recording = self.seed()
        before = list(ReplayPlayerStats.objects.values())
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive'):
            call_command('store_replays', stdout=StringIO())
        recording.refresh_from_db()
        self.assertEqual(recording.status, 'ready')
        self.assertEqual(recording.raw_response, self.result)
        self.assertEqual(list(ReplayPlayerStats.objects.values()), before)
        with patch('tournament.services.replay_storage.download_replay') as download:
            call_command('store_replays', stdout=StringIO())
            download.assert_not_called()
        recording.replay_file.storage.delete(recording.replay_file.name)
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2changed'),
            self.assertRaises(CommandError),
        ):
            call_command('store_replays', stdout=StringIO(), stderr=StringIO())
        recording.refresh_from_db()
        self.assertEqual(recording.status, 'ready')
        self.assertEqual(recording.raw_response, self.result)
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive'):
            self.assertEqual(recording_bytes(recording), b'HBR2archive')

    def test_corrupt_archive_is_not_silently_replaced(self):
        recording = self.seed()
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive'):
            recording_bytes(recording)
        with recording.replay_file.open('wb') as target:
            target.write(b'corrupt')
        with patch('tournament.services.replay_storage.download_replay') as download:
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                recording_bytes(recording)
            download.assert_not_called()

    def test_archive_deleted_only_after_recording_deletion_commits(self):
        recording = self.seed()
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive'):
            recording_bytes(recording)
        storage, name = recording.replay_file.storage, recording.replay_file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.match.delete()
            self.assertTrue(storage.exists(name))
        self.assertFalse(storage.exists(name))

    def test_identical_archives_share_flat_checksum_path_and_survive_partial_deletion(self):
        first = self.seed()
        second = ReplayRecording.objects.create(match=self.match, source_key='powtorki:duplicate', replay_url=self.url)
        data = b'HBR2archive'
        with patch('tournament.services.replay_storage.download_replay', return_value=data):
            recording_bytes(first)
            recording_bytes(second)
        first.refresh_from_db()
        second.refresh_from_db()
        name = f'replays/{hashlib.sha256(data).hexdigest()}.hbr2'
        self.assertEqual(first.replay_file.name, name)
        self.assertEqual(second.replay_file.name, name)
        storage = first.replay_file.storage
        self.assertEqual(storage.listdir('replays'), ([], [name.split('/')[-1]]))
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(storage.exists(name))
        with patch('tournament.services.replay_storage.download_replay') as download:
            self.assertEqual(recording_bytes(second), data)
            download.assert_not_called()
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(storage.exists(name))

    def test_store_replays_reports_progress_before_download_and_continues_after_failure(self):
        first = self.seed()
        second = ReplayRecording.objects.create(
            match=self.match, source_key='powtorki:second', replay_url='https://replay.thehax.pl/second'
        )
        output, errors = StringIO(), StringIO()

        def download(url):
            recording = first if url == first.replay_url else second
            index = 1 if recording.pk == first.pk else 2
            self.assertIn(
                f'[{index}/2] Match {self.match.pk}, recording {recording.pk}: Downloading replay...', output.getvalue()
            )
            if index == 1:
                raise RuntimeError('Host unavailable')
            return b'HBR2archive'

        with (
            patch('tournament.services.replay_storage.download_replay', side_effect=download),
            self.assertRaises(CommandError),
        ):
            call_command('store_replays', stdout=output, stderr=errors)
        self.assertIn('Storing replay files for 2 recordings...', output.getvalue())
        self.assertIn('Downloaded and stored: 1; already stored: 0; failed: 1', output.getvalue())
        self.assertIn(f'recording {first.pk}: Failed', errors.getvalue())
        self.assertIn('Host unavailable', errors.getvalue())
        output = StringIO()
        with patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2archive') as retry:
            call_command('store_replays', stdout=output)
            retry.assert_called_once_with(first.replay_url)
        self.assertIn('Checking stored file...', output.getvalue())
        self.assertIn('Downloaded and stored: 1; already stored: 1; failed: 0', output.getvalue())

    def test_reanalysis_replaces_old_heatmap_response_and_preserves_part_corrections(self):
        old = copy.deepcopy(self.result)
        old['games'][0]['players'][0]['maps']['heatmap'] = [{'x': 1, 'y': 2, 'ticks': 100}]
        recording = self.seed(old)
        part = active_parts(self.match)[0]
        part.label_override = 'Keep label'
        part.red_is_home_override = False
        part.save()
        with (
            patch('tournament.services.replay_storage.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            self.assertEqual(ingest_match(self.match.pk, force=True)['failed_recordings'], 0)
        recording.refresh_from_db()
        part.refresh_from_db()
        self.assertEqual(recording.raw_response, self.result)
        for game in recording.raw_response['games']:
            for player in game['players']:
                self.assertNotIn('heatmap', player.get('maps', {}))
        self.assertEqual(part.label, 'Keep label')
        self.assertFalse(part.red_is_home)

    def test_player_rows_are_identified_by_game_nickname_and_side_not_engine_id(self):
        recording = self.seed()
        before = list(ReplayPlayerStats.objects.order_by('pk').values('pk', 'game_id', 'nick', 'side'))
        raw = copy.deepcopy(self.result)
        for game in raw['games']:
            for index, player in enumerate(game['players']):
                player['id'] = f'changed-connection-{index}'
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        self.assertEqual(before, list(ReplayPlayerStats.objects.order_by('pk').values('pk', 'game_id', 'nick', 'side')))
