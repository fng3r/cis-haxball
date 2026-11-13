from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from tournament.models import League, Match, RegularStage, Season, Team, TourNumber

from .models import ReservationEntry, ReservationHost


@override_settings(TIME_ZONE='Europe/Moscow', BASE_URL='https://cis-haxball.ru/')
class ReservationsApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user(username='private-author', email='private@example.com')
        cls.host = ReservationHost.objects.create(name='Broadcast room', codename='room-ruid', is_active=True)
        cls.home = Team.objects.create(title='Home team', short_title='HOME', slug='home')
        cls.away = Team.objects.create(title='Away team', short_title='AWAY', slug='away')
        season = Season.objects.create(title='Season', number=1, is_active=False)
        cls.league = League.objects.create(title='Premier league', slug='premier', championship=season)
        stage = RegularStage.objects.create(league=cls.league, order=1)
        tour = TourNumber.objects.create(league=cls.league, stage=stage, number=1)
        cls.match = Match.objects.create(league=cls.league, numb_tour=tour, team_home=cls.home, team_guest=cls.away)

    def setUp(self):
        self.url = reverse('reservations_api')
        self.start = datetime(2026, 11, 13, tzinfo=ZoneInfo('Europe/Moscow'))

    def reserve(self, starts_at=None, **kwargs):
        return ReservationEntry.objects.create(
            author=self.author,
            match=kwargs.pop('match', self.match),
            host=kwargs.pop('host', self.host),
            time_date=starts_at or self.start,
            **kwargs,
        )

    def get_schedule(self, day='2026-11-13'):
        return self.client.get(self.url, {'date': day})

    def test_public_contract_and_canonical_match_url(self):
        entry = self.reserve()
        self.assertEqual(self.url, '/api/reservations/')
        response = self.client.get(self.url, {'date': '2026-11-13'}, secure=True, HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(
            response.json(),
            {
                'date': '2026-11-13',
                'timezone': 'Europe/Moscow',
                'reservations': [
                    {
                        'id': entry.pk,
                        'startsAt': '2026-11-13T00:00:00+03:00',
                        'host': {'codename': 'room-ruid', 'name': 'Broadcast room'},
                        'match': {
                            'id': self.match.pk,
                            'url': 'https://cis-haxball.ru' + self.match.get_absolute_url(),
                            'season': {'id': self.league.championship_id, 'name': 'Season'},
                            'league': {'id': self.league.pk, 'name': 'Premier league'},
                            'stage': None,
                            'group': None,
                            'tour': {'id': self.match.numb_tour_id, 'name': '1 тур'},
                            'series': None,
                            'date': None,
                            'officialScore': [0, 0],
                            'isPlayed': False,
                        },
                        'teams': {
                            'home': {
                                'id': self.home.pk,
                                'name': 'Home team',
                                'shortName': 'HOME',
                                'logo': 'https://cis-haxball.ru/media/team_logos/default.png',
                            },
                            'away': {
                                'id': self.away.pk,
                                'name': 'Away team',
                                'shortName': 'AWAY',
                                'logo': 'https://cis-haxball.ru/media/team_logos/default.png',
                            },
                        },
                    }
                ],
            },
        )
        self.assertNotIn('private', response.content.decode())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_local_day_boundaries_and_current_timezone_override(self):
        self.reserve(self.start - timedelta(microseconds=1))
        first = self.reserve(self.start.astimezone(ZoneInfo('UTC')))
        last = self.reserve(self.start + timedelta(days=1, microseconds=-1))
        self.reserve(self.start + timedelta(days=1))
        with timezone.override('America/New_York'):
            data = self.get_schedule().json()
        self.assertEqual([r['id'] for r in data['reservations']], [first.pk, last.pk])
        self.assertEqual(data['reservations'][1]['startsAt'], '2026-11-13T23:59:59.999999+03:00')

    def test_includes_earlier_today(self):
        entry = self.reserve(self.start + timedelta(hours=1))
        with patch('django.utils.timezone.now', return_value=self.start + timedelta(hours=20)):
            self.assertEqual([r['id'] for r in self.get_schedule().json()['reservations']], [entry.pk])

    def test_includes_played_matches_but_filters_cancelled_inactive_and_missing_hosts(self):
        available = self.reserve()
        self.reserve(cancelled_at=self.start)
        inactive = ReservationHost.objects.create(name='Inactive', codename='inactive', is_active=False)
        self.reserve(host=inactive)
        self.reserve(host=None)
        played_match = Match.objects.create(
            league=self.league, numb_tour=self.match.numb_tour, team_home=self.home, team_guest=self.away
        )
        Match.objects.filter(pk=played_match.pk).update(is_played=True)
        played = self.reserve(match=played_match)
        reservations = self.get_schedule().json()['reservations']
        self.assertEqual([r['id'] for r in reservations], [available.pk, played.pk])
        self.assertTrue(reservations[1]['match']['isPlayed'])

    def test_chronological_order_with_id_ties_and_constant_queries(self):
        late = self.reserve(self.start + timedelta(hours=3))
        first = self.reserve(self.start + timedelta(hours=1))
        second = self.reserve(self.start + timedelta(hours=1))
        with CaptureQueriesContext(connection) as queries:
            response = self.get_schedule()
        self.assertEqual([r['id'] for r in response.json()['reservations']], [first.pk, second.pk, late.pk])
        self.assertEqual(len(queries), 2)
        sql = queries[0]['sql']
        self.assertIn('"time_date" >=', sql)
        self.assertIn('"time_date" <', sql)
        self.assertNotIn('django_datetime_cast_date', sql)
        self.assertNotIn('auth_user', sql)

    def test_empty_day(self):
        self.assertEqual(
            self.get_schedule().json(),
            {
                'date': '2026-11-13',
                'timezone': 'Europe/Moscow',
                'reservations': [],
            },
        )

    def test_strict_validation_without_queries(self):
        invalid = [
            {},
            {'date': ''},
            {'date': '2026-2-03'},
            {'date': '2026-11-3'},
            {'date': '2026-02-29'},
            {'date': '2026-11-31'},
            {'date': '0000-01-01'},
            {'date': '20261113'},
            {'date': '2026-W46-5'},
            {'date': '2026-11-13T00:00:00+03:00'},
            {'date': ' 2026-11-13'},
            {'date': '2026-11-13\n'},
            {'date': '２０２６-１１-１３'},
            {'date': ['2026-11-13', '2026-11-14']},
            {'date': '9999-12-31'},
        ]
        for params in invalid:
            with self.subTest(params=params), self.assertNumQueries(0):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response['Content-Type'], 'application/json')
                self.assertEqual(set(response.json()), {'error'})

    def test_valid_leap_day_and_year_boundary(self):
        for day in ['2024-02-29', '2026-12-31']:
            with self.subTest(day=day):
                self.assertEqual(self.get_schedule(day).status_code, 200)

    def test_uses_configured_site_timezone(self):
        self.reserve(self.start)
        with override_settings(TIME_ZONE='UTC'):
            data = self.get_schedule('2026-11-12').json()
        self.assertEqual(data['timezone'], 'UTC')
        self.assertEqual(data['reservations'][0]['startsAt'], '2026-11-12T21:00:00+00:00')

    def test_post_is_not_allowed(self):
        with self.assertNumQueries(0):
            response = self.client.post(self.url, {'date': '2026-11-13'})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Allow'], 'GET')

    def test_analyzer_context_multistage_group_playoff_and_series(self):
        from tournament.models import Group, GroupStage, MatchSeries, PlayOffStage

        group_stage = GroupStage.objects.create(league=self.league, order=2)
        group = Group.objects.create(stage=group_stage, name='Group A')
        playoff = PlayOffStage.objects.create(league=self.league, order=3)
        semifinal = TourNumber.objects.create(league=self.league, stage=playoff, number=1)
        final = TourNumber.objects.create(league=self.league, stage=playoff, number=2)
        series = MatchSeries.objects.create(tour=semifinal, bracket_slot=1, team_home=self.home, team_guest=self.away)
        Match.objects.filter(pk=self.match.pk).update(stage=playoff, group=group, numb_tour=semifinal, series=series)
        second = Match.objects.create(
            league=self.league,
            stage=playoff,
            numb_tour=semifinal,
            series=series,
            team_home=self.away,
            team_guest=self.home,
        )
        self.match.refresh_from_db()
        self.reserve()
        self.reserve(match=second)
        with self.assertNumQueries(4):
            entries = self.get_schedule().json()['reservations']
        context = entries[0]['match']
        self.assertEqual(context['stage'], {'id': playoff.pk, 'name': str(playoff)})
        self.assertEqual(context['group'], {'id': group.pk, 'name': 'Group A'})
        self.assertEqual(context['tour'], {'id': semifinal.pk, 'name': '1/2 Финала'})
        self.assertEqual(context['series'], {'id': series.pk, 'matchNumber': 1})
        self.assertEqual(entries[1]['match']['series'], {'id': series.pk, 'matchNumber': 2})
        Match.objects.filter(pk=second.pk).update(numb_tour=final)
        self.assertEqual(self.get_schedule().json()['reservations'][1]['match']['tour']['name'], 'Финал')
        TourNumber.objects.filter(pk=final.pk).update(name='Grand Final')
        self.assertEqual(self.get_schedule().json()['reservations'][1]['match']['tour']['name'], 'Grand Final')
        Match.objects.filter(pk=second.pk).update(series=None)
        self.assertIsNone(self.get_schedule().json()['reservations'][0]['match']['series'])

    def test_day_bounds_follow_dst_in_configured_timezone(self):
        with override_settings(TIME_ZONE='America/New_York'):
            start = datetime(2026, 11, 1, tzinfo=ZoneInfo('America/New_York'))
            self.reserve(start - timedelta(microseconds=1))
            first = self.reserve(start)
            last = self.reserve(start + timedelta(days=1, microseconds=-1))
            self.reserve(start + timedelta(days=1))
            entries = self.get_schedule('2026-11-01').json()['reservations']
        self.assertEqual([r['id'] for r in entries], [first.pk, last.pk])
        self.assertTrue(entries[0]['startsAt'].endswith('-04:00'))
        self.assertTrue(entries[1]['startsAt'].endswith('-05:00'))

    def test_nullable_season_logo_and_match_calendar_date(self):
        League.objects.filter(pk=self.league.pk).update(championship=None)
        Team.objects.filter(pk=self.home.pk).update(logo='')
        Match.objects.filter(pk=self.match.pk).update(match_date='2026-11-14')
        self.reserve()
        entry = self.get_schedule().json()['reservations'][0]
        self.assertIsNone(entry['match']['season'])
        self.assertIsNone(entry['teams']['home']['logo'])
        self.assertEqual(entry['match']['date'], '2026-11-14')
        self.assertEqual(entry['startsAt'], '2026-11-13T00:00:00+03:00')
