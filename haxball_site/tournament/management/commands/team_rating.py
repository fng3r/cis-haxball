from django.core.management.base import BaseCommand
from django.db.models import F, Q
from django.utils import timezone

from ...models import Season, SeasonTeamRating, TeamRating, TeamRatingVersion


class Command(BaseCommand):
    help = 'Calculate team rating'

    def add_arguments(self, parser):
        parser.add_argument('source_season', type=int)
        parser.add_argument('mode', type=str, choices=['points', 'rating', 'all'], default='all')

    def handle(self, *args, **options):
        source_season_number = options['source_season']
        mode = options['mode']
        source_season = Season.objects.get(number=source_season_number)
        season = source_season

        if mode in ['points', 'all']:
            season_points = self.get_season_points(season)
            for team in season_points:
                SeasonTeamRating(season=season, team=team, points_for_matches=season_points[team]).save()
            print(f'Season points calculation for season "{source_season.title}" is completed')

        if mode in ['rating', 'all']:
            last_version = TeamRatingVersion.objects.order_by('-number').first()
            version = last_version.number + 1 if last_version else 1
            season_count = 0
            if not source_season.title.startswith('ЧР'):
                source_season_number += 1
                print(f'Rating calculation for season "{source_season.title}" is skipped')
                return

            season = source_season
            overall_rating = {}
            while season_count < 6 and season.number > 5:
                self.calculate_rating_points(overall_rating, season, season_count)

                previous_season = (
                    Season.objects.filter(number__lt=season.number, title__contains='ЧР').order_by('-number').first()
                )
                if not previous_season:
                    break

                season = previous_season
                season_count += 1

            ordered_rating = [(k, v) for k, v in sorted(overall_rating.items(), key=lambda item: item[1], reverse=True)]

            rating_version = TeamRatingVersion(number=version, date=timezone.localdate(), related_season=source_season)
            rating_version.save()
            for rank, entry in enumerate(ordered_rating, 1):
                TeamRating(version=rating_version, rank=rank, team=entry[0], total_points=entry[1]).save()
            print(f'Rating calculation for season "{source_season.title}" is completed')

    def calculate_rating_points(self, overall_rating, season, season_count):
        season_weights = [1, 1, 1, 0.9, 0.8, 0.7]
        season_rating = SeasonTeamRating.objects.filter(season=season)
        season_weight = season_weights[season_count]
        for sre in season_rating:
            team = sre.team
            if team not in overall_rating:
                overall_rating[team] = 0
            overall_rating[team] += round(sre.total_points() * season_weight, 2)

        if season.bound_season:
            self.calculate_rating_points(overall_rating, season.bound_season, season_count)

    def get_season_points(self, season):
        season_rating = {}
        season_leagues = season.tournaments_in_season.all()
        for league in season_leagues:
            teams = league.teams.all()
            league_weight = self.get_league_weight(league)
            for team in teams:
                matches = league.matches_in_league.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)

                wins = (
                    matches.filter(team_home=team, score_home__gt=F('score_guest')).count()
                    + matches.filter(team_guest=team, score_guest__gt=F('score_home')).count()
                )
                draws = matches.filter(Q(team_home=team) | Q(team_guest=team), score_home=F('score_guest')).count()
                points = (wins * 1 + draws * 0.5) * league_weight
                if team not in season_rating:
                    season_rating[team] = 0
                season_rating[team] += points

        return season_rating

    @staticmethod
    def get_league_weight(league):
        match league.title:
            case 'Высшая лига' | 'Единая лига' | 'Кубок Высшей лиги':
                return 1
            case 'Кубок России' | 'Лига Чемпионов':
                return 0.75
            case 'Первая лига' | 'Кубок Первой лиги' | 'Кубок лиги':
                return 0.5
            case t if t.startswith('Первая лига'):
                return 0.5
            case 'Вторая лига' | 'Кубок Второй лиги':
                return 0.25

        raise ValueError(f'Unknown league: {league.title}')
