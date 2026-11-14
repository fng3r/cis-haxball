from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from .admin import ReplayLeagueFilter, replay_match_filters
from .models import (
    League,
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
    MatchReplayStatsStatus,
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


class ReplayAdminTests(TestCase):
    model_paths = {
        ReplayRecording: 'match',
        ReplayGame: 'recording__match',
        ReplayMatchPart: 'match',
        ReplayTeamStats: 'game__recording__match',
        ReplayPlayerStats: 'game__recording__match',
        MatchReplayStatsStatus: 'match',
        MatchReplay: 'match',
        MatchReplayStats: 'match',
        MatchReplayStatsPlayer: 'replay_stats__match',
    }

    @classmethod
    def setUpTestData(cls):
        cls.editor = User.objects.create_superuser('replay-admin-editor', password='test')
        cls.season = Season.objects.create(
            title='Replay admin', number=99, is_active=False, type='russian_championship'
        )
        cls.league = League.objects.create(championship=cls.season, title='League', slug='replay-admin')
        League.objects.create(championship=cls.season, title='Other league', slug='replay-admin-other')
        stage = RegularStage.objects.create(league=cls.league, order=1, type='REG')
        # TourNumber.__str__ checks whether the league has multiple stages.
        RegularStage.objects.create(league=cls.league, order=2, type='REG')
        tour = TourNumber.objects.create(league=cls.league, stage=stage, number=3)
        home = Team.objects.create(title='Home', short_title='H', slug='replay-admin-home')
        away = Team.objects.create(title='Away', short_title='A', slug='replay-admin-away')
        cls.matches = []
        for index in range(20):
            match = Match.objects.create(
                league=cls.league,
                stage=stage,
                numb_tour=tour,
                team_home=home,
                team_guest=away,
            )
            cls.matches.append(match)
            player = Player.objects.create(nickname=f'Player {index}')
            recording = ReplayRecording.objects.create(
                match=match,
                source_key=f'source:{index}',
                status='ready',
                raw_response={'sentinel': 'raw recording payload'},
            )
            game = ReplayGame.objects.create(recording=recording, engine_game_id=0, stadium_name='Test stadium')
            ReplayMatchPart.objects.create(match=match, game=game, included=index % 2 == 0)
            side = 'red' if index % 2 == 0 else 'blue'
            ReplayTeamStats.objects.create(game=game, side=side)
            ReplayPlayerStats.objects.create(
                game=game,
                nick=player.nickname,
                side=side,
                player=player if index % 2 == 0 else None,
            )
            MatchReplayStatsStatus.objects.create(match=match, status='success')
            legacy = MatchReplay.objects.create(
                match=match,
                replay_url=f'https://replay.thehax.pl/test-{index}',
                raw_stats_json=[{'sentinel': 'legacy raw payload'}],
                status='ready',
            )
            stats = MatchReplayStats.objects.create(match=match, match_replay=legacy)
            MatchReplayStatsPlayer.objects.create(replay_stats=stats, player=player, team=home, nick=player.nickname)

    def request(self, model, params=None):
        path = reverse(f'admin:tournament_{model._meta.model_name}_changelist')
        request = RequestFactory().get(path, params or {})
        request.user = self.editor
        request.session = {}
        request._messages = FallbackStorage(request)
        request.resolver_match = resolve(path)
        return request

    def render_list(self, model, page_size):
        model_admin = admin.site._registry[model]
        with patch.object(model_admin, 'list_per_page', page_size), CaptureQueriesContext(connection) as queries:
            response = model_admin.changelist_view(self.request(model))
            response.render()
        self.assertEqual(response.status_code, 200)
        return queries

    def test_rendered_list_query_count_does_not_grow_with_row_count(self):
        for model in self.model_paths:
            with self.subTest(model=model.__name__):
                self.render_list(model, 1)  # Warm template/content-type caches consistently.
                one = self.render_list(model, 1)
                twenty = self.render_list(model, 20)
                self.assertLessEqual(len(twenty), len(one) + 1, (model.__name__, len(one), len(twenty)))
                self.assertFalse(any('"raw_response"' in q['sql'] or '"raw_stats_json"' in q['sql'] for q in twenty))

    def test_competition_and_match_filters_work_on_every_replay_list(self):
        for model, path in self.model_paths.items():
            for field, value in (
                (f'{path}__league__championship__id__exact', self.season.pk),
                (f'{path}__league__id__exact', self.league.pk),
                (f'{path}__stage__type__exact', 'REG'),
                (f'{path}__numb_tour__number', 3),
                (f'{path}__id', self.matches[0].pk),
            ):
                with self.subTest(model=model.__name__, field=field):
                    model_admin = admin.site._registry[model]
                    filtered = model_admin.get_changelist_instance(self.request(model, {field: value})).queryset
                    self.assertTrue(filtered.exists())
                    self.assertEqual(set(filtered.values_list(f'{path}__league_id', flat=True)), {self.league.pk})
                    rejected = 'PO' if 'stage__type' in field else 999999
                    filtered = model_admin.get_changelist_instance(self.request(model, {field: rejected})).queryset
                    self.assertFalse(filtered.exists())
            self.assertEqual(len(replay_match_filters(path)), 5)

    def test_state_and_resolution_filters_do_not_duplicate_rows(self):
        for model, params, expected in (
            (ReplayRecording, {'status__exact': 'failed'}, 0),
            (ReplayGame, {'available__exact': '1'}, 20),
            (ReplayMatchPart, {'included__exact': '0'}, 10),
            (ReplayMatchPart, {'included_override__isnull': 'True'}, 20),
            (ReplayTeamStats, {'side__exact': 'red', 'game__match_part__included__exact': '1'}, 10),
            (ReplayPlayerStats, {'player_resolution': 'unresolved'}, 10),
            (ReplayPlayerStats, {'player_resolution': 'resolved'}, 10),
            (MatchReplayStatsPlayer, {'player_resolution': 'unresolved'}, 0),
        ):
            with self.subTest(model=model.__name__, params=params):
                cl = admin.site._registry[model].get_changelist_instance(self.request(model, params))
                self.assertEqual(cl.queryset.count(), expected)
                self.assertEqual(len(set(cl.queryset.values_list('pk', flat=True))), expected)

    def test_raw_payloads_are_still_accessible_on_recording_detail(self):
        for model, field in ((ReplayRecording, 'raw_response'), (MatchReplay, 'raw_stats_json')):
            with self.subTest(model=model.__name__):
                row = admin.site._registry[model].get_queryset(self.request(model)).first()
                self.assertIn(field, row.get_deferred_fields())
                with self.assertNumQueries(1):
                    self.assertTrue(getattr(row, field))

    def test_league_filter_labels_do_not_query_each_season(self):
        League.objects.bulk_create(
            [League(championship=self.season, title=f'League {i}', slug=f'filter-league-{i}') for i in range(20)]
        )
        with self.assertNumQueries(1):
            league_filter = ReplayLeagueFilter(
                Match._meta.get_field('league'),
                self.request(ReplayRecording),
                {},
                ReplayRecording,
                admin.site._registry[ReplayRecording],
                'match__league',
            )
            self.assertEqual(len(league_filter.lookup_choices), 22)
