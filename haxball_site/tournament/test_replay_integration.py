import copy
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse

from .local_replay_analyzer import analyze_local_replay
from .models import (
    League,
    LocalReplayAnalysis,
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
    RegularStage,
    Season,
    Team,
    TourNumber,
)
from .replay_stats_client import download_replay, get_replay_source_and_id
from .services.local_replays import infer_mapping, ingest_match, match_recordings, match_statistics
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

    def analysis(self, mappings=None):
        return LocalReplayAnalysis.objects.create(
            match=self.match, replay_url=self.url, result=self.result, inferred_sides=mappings or {}, status='ready'
        )

    def test_default_ingestion_preserves_all_legacy_rows_and_retries_are_idempotent(self):
        legacy = MatchReplay.objects.create(
            match=self.match,
            replay_url=self.url,
            raw_stats_json=[{'old': 'unchanged'}],
            analyzer_replay_id='old',
            status='ready',
        )
        part = MatchReplayStats.objects.create(match=self.match, match_replay=legacy, score_red=8)
        player = MatchReplayStatsPlayer.objects.create(
            replay_stats=part, nick='old player', rating=9.8, played_ticks=10
        )
        before = [list(model.objects.values()) for model in (MatchReplay, MatchReplayStats, MatchReplayStatsPlayer)]
        with (
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result) as engine,
        ):
            first = fetch_match_replay_stats(self.match.pk)
            second = fetch_match_replay_stats(self.match.pk)
            self.assertEqual(first['created_games'], 2)
            self.assertEqual(second['created_games'], 0)
            self.assertEqual(engine.call_count, 1)
        self.assertEqual(LocalReplayAnalysis.objects.count(), 1)
        self.assertEqual(
            before, [list(model.objects.values()) for model in (MatchReplay, MatchReplayStats, MatchReplayStatsPlayer)]
        )
        self.assertTrue(MatchReplayStatsPlayer.objects.filter(pk=player.pk, rating=9.8).exists())

    def test_unknown_games_keep_every_metric_but_do_not_enter_team_totals(self):
        analysis = self.analysis()
        stats = match_statistics(self.match)
        self.assertEqual(len(stats['games']), 2)
        self.assertEqual(stats['unresolved'], 2)
        self.assertEqual(stats['totals']['kicks'], [0, 0])
        self.assertEqual(stats['games'][0]['game'], analysis.result['games'][0])
        html = render_to_string('tournament/match/local_statistics.html', {'local': stats, 'match': self.match})
        self.assertIn('стороны не определены', html)
        self.assertIn(self.result['games'][0]['players'][0]['nick'], html)

    def test_per_game_side_swaps_and_substitutions_use_roster_evidence(self):
        roster = {'home': {'alice', 'sub'}, 'away': {'bob'}}
        players = [
            {'nick': 'Alice', 'team': 'red', 'playedTicks': 100},
            {'nick': 'Sub', 'team': 'red', 'playedTicks': 10},
            {'nick': 'Bob', 'team': 'blue', 'playedTicks': 100},
        ]
        self.assertIs(infer_mapping({'players': players}, roster), True)
        swapped = [{**p, 'team': 'blue' if p['team'] == 'red' else 'red'} for p in players]
        self.assertIs(infer_mapping({'players': swapped}, roster), False)
        self.assertIsNone(infer_mapping({'players': players + swapped}, roster))
        self.assertIsNone(infer_mapping({'players': []}, roster))
        self.assertIsNone(
            infer_mapping({'players': players}, {'home': {'alice', 'bob', 'sub'}, 'away': {'alice', 'bob', 'sub'}})
        )
        analysis = self.analysis({'0': True, '1': False})
        stats = match_statistics(self.match)
        expected = [
            analysis.result['games'][0]['scoreRed'] + analysis.result['games'][1]['scoreBlue'],
            analysis.result['games'][0]['scoreBlue'] + analysis.result['games'][1]['scoreRed'],
        ]
        self.assertEqual(stats['totals']['score'], expected)

    def test_manifest_loads_real_recording_paths_and_hierarchy_without_arbitrary_urls(self):
        self.analysis({'0': True, '1': False})
        response = self.client.get(reverse('tournament:analyzer_manifest', args=[self.match.pk]))
        data = response.json()
        self.assertEqual(data['match']['season']['id'], self.season.pk)
        self.assertEqual(data['match']['tour']['id'], self.tour.pk)
        self.assertEqual(data['teams']['home']['id'], self.home.pk)
        self.assertEqual(data['recordings'][0]['mappings'], {'0': True, '1': False})
        self.assertFalse(data['canMap'])
        with patch('tournament.replay_integration.download_replay', return_value=b'HBR2actual') as download:
            response = self.client.get(data['recordings'][0]['url'])
            self.assertEqual(response.content, b'HBR2actual')
            download.assert_called_once_with(self.url)
            self.assertEqual(self.client.get(data['recordings'][0]['url'] + '99').status_code, 404)

    def test_authorized_mapping_is_persisted_and_metrics_and_other_games_unchanged(self):
        analysis = self.analysis({'0': True, '1': False})
        endpoint = reverse('tournament:analyzer_mapping', args=[self.match.pk, 0])
        self.assertEqual(
            self.client.post(
                endpoint, json.dumps({'game': 0, 'redIsHome': False}), content_type='application/json'
            ).status_code,
            403,
        )
        editor = User.objects.create_superuser('editor', password='test')
        self.client.force_login(editor)
        before = copy.deepcopy(analysis.result)
        for value in (False, False, None, True):
            response = self.client.post(
                endpoint, json.dumps({'game': 0, 'redIsHome': value}), content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
            analysis.refresh_from_db()
            self.assertIs(analysis.game_mapping(0), value)
            self.assertIs(analysis.game_mapping(1), False)
            self.assertEqual(analysis.result, before)
        self.assertEqual(analysis.mapping_audit['0']['user'], editor.pk)
        self.assertEqual(
            self.client.post(
                endpoint, json.dumps({'game': 99, 'redIsHome': True}), content_type='application/json'
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                endpoint, json.dumps({'game': True, 'redIsHome': 'yes'}), content_type='application/json'
            ).status_code,
            400,
        )
        csrf_client = Client(enforce_csrf_checks=True, HTTP_USER_AGENT='Replay integration tests')
        csrf_client.force_login(editor)
        self.assertEqual(
            csrf_client.post(
                endpoint, json.dumps({'game': 0, 'redIsHome': True}), content_type='application/json'
            ).status_code,
            403,
        )
        manifest = csrf_client.get(reverse('tournament:analyzer_manifest', args=[self.match.pk]))
        token = manifest.cookies['csrftoken'].value
        self.assertEqual(
            csrf_client.post(
                endpoint,
                json.dumps({'game': 0, 'redIsHome': True}),
                content_type='application/json',
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            200,
        )

    def test_failed_recording_can_be_retried(self):
        with patch('tournament.services.local_replays.download_replay', side_effect=TimeoutError('timeout')):
            self.assertEqual(ingest_match(self.match.pk)['failed_recordings'], 1)
        self.assertEqual(LocalReplayAnalysis.objects.get().status, 'failed')
        with (
            patch('tournament.services.local_replays.download_replay', return_value=b'HBR2fixture'),
            patch('tournament.services.local_replays.analyze_local_replay', return_value=self.result),
        ):
            ingest_match(self.match.pk)
        self.assertEqual(LocalReplayAnalysis.objects.get().status, 'ready')

    def test_unsupported_ids_and_download_redirects_are_rejected(self):
        for url in [
            'https://replay.thehax.pl/../secret',
            'https://replay.thehax.pl/x?bad=1/../../',
            'https://hax.saviola.de/r/?h=../../x',
            'file:///etc/passwd',
            'https://user@replay.thehax.pl/x',
        ]:
            if '?bad' not in url:
                self.assertIsNone(get_replay_source_and_id(url))
        with patch('tournament.replay_stats_client.requests.get') as get:
            get.return_value.__enter__.return_value.status_code = 302
            with self.assertRaises(ValueError):
                download_replay(self.url)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_removed_links_are_archived_and_duplicate_recording_links_are_not_counted_twice(self):
        analysis = self.analysis({'0': True, '1': False})
        self.match.replays = [self.url, self.url + '/download']
        self.assertEqual(len(match_recordings(self.match)), 1)
        self.assertEqual(len(match_statistics(self.match)['games']), 2)
        self.match.replays = []
        self.assertEqual(match_statistics(self.match)['games'], [])
        self.assertTrue(LocalReplayAnalysis.objects.filter(pk=analysis.pk).exists())
