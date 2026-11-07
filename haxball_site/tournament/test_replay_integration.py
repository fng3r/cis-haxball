import copy
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from .local_replay_analyzer import analyze_local_replay
from .models import (
    League,
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
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
    infer_mapping,
    ingest_match,
    materialize,
    reconcile_parts,
)
from .services.replay_presentation import statistics
from .tasks import fetch_match_replay_stats


class LocalReplayIntegrationTests(TestCase):
    def setUp(self):
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
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
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
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            ingest_match(self.match.pk, force=True)
        recording.refresh_from_db()
        first_hash = recording.content_sha256
        response_hash = recording.response_sha256
        with (
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
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
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
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
        with patch('tournament.services.local_replays.download_replay') as download:
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
        with patch('tournament.replay_integration.download_replay', return_value=b'HBR2actual') as download:
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
        part.included = False
        part.save()
        self.assertEqual(len(statistics(self.match)['parts_summary']), 1)

    def test_short_scoreless_restarts_are_excluded_once(self):
        raw = copy.deepcopy(self.result)
        raw['games'][0].update(gameTicks=1, scoreRed=0, scoreBlue=0)
        recording = ReplayRecording.objects.create(
            match=self.match, source_key='powtorki:test-recording', replay_url=self.url
        )
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        part = ReplayMatchPart.objects.get(game__engine_game_id=raw['games'][0]['id'])
        self.assertFalse(part.included)
        part.included = True
        part.save()
        materialize(recording, raw, {'home': set(), 'away': set()}, {})
        part.refresh_from_db()
        self.assertTrue(part.included)

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
        from io import StringIO

        from django.core.management import call_command

        with patch('tournament.tasks.fetch_match_replay_stats.delay') as queued:
            call_command('build_match_stats', match_ids=[self.match.pk], reanalyze=True, stdout=StringIO())
            queued.assert_called_once_with(self.match.pk, force=True)

    def test_match_deletion_cascades_without_leaving_protected_part_dependencies(self):
        self.seed()
        self.match.delete()
        self.assertFalse(ReplayRecording.objects.exists())
        self.assertFalse(ReplayMatchPart.objects.exists())

    def test_legacy_statistics_keep_the_existing_source_and_metrics(self):
        from types import SimpleNamespace

        from .services.replay_stats import MatchReplayStatsAggregator

        recording = MatchReplay.objects.create(match=self.match, replay_url=self.url, analyzer_replay_id='legacy-id')
        part = MatchReplayStats.objects.create(match=self.match, match_replay=recording, score_red=3)
        MatchReplayStatsPlayer.objects.create(replay_stats=part, nick='Legacy player', rating=8.5, played_ticks=3600)
        agg = MatchReplayStatsAggregator(self.match, [part]).build()
        html = render_to_string(
            'tournament/match/statistics.html',
            {
                'match': self.match,
                'match_replay_stats_aggregated': agg,
                'replay_stats_status': SimpleNamespace(status='success'),
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
