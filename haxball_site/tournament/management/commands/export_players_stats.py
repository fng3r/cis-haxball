import csv
from collections import defaultdict
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max

from ...models import Player, PlayerMatchStatistics, PlayerRating, PlayerRatingVersion, Season

SEASON_NUMBERS = (23, 24)
HEADERS = [
    'Игрок',
    'Рейтинг',
    'Уровень',
    'ЧР #16',
    'ЧР #16 (Команды)',
    'ЛЧ #6',
    'ЛЧ #6 (Команды)',
    'Пропущено сезонов',
]
DEFAULT_SITE_URL = 'https://cis-haxball.ru'


@dataclass
class PlayerExportRow:
    player: Player
    rating: int | None
    grade: str
    matches_by_season: dict[int, int]
    teams_by_season: dict[int, list[str]]
    skipped_seasons: str
    last_season_number: int | None


class Command(BaseCommand):
    help = 'Export players stats with rating to CSV for Google Spreadsheet'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='Path to output .csv file')
        parser.add_argument(
            '-V',
            '--rating-version',
            dest='rating_version',
            type=int,
            help='Rating version number (defaults to latest)',
        )
        parser.add_argument(
            '--site-url',
            type=str,
            default=DEFAULT_SITE_URL,
            help=f'Site base URL for profile hyperlinks (default: {DEFAULT_SITE_URL})',
        )

    def handle(self, *args, **options):
        filename = options['filename']
        site_url = options['site_url'].rstrip('/')
        rating_version_number = options['rating_version']

        _ = self._load_seasons()
        rating_version = self._load_rating_version(rating_version_number)

        player_ids = self._collect_player_ids(rating_version)
        players = {
            player.id: player
            for player in Player.objects.filter(id__in=player_ids).select_related('name__user_profile')
        }

        ratings = {
            rating.player_id: rating
            for rating in PlayerRating.objects.filter(version=rating_version, player_id__in=player_ids)
        }
        match_counts, teams_by_player_season = self._collect_season_stats(player_ids)
        last_season_by_player = self._collect_last_seasons(player_ids)

        rows = []
        for player_id, player in players.items():
            rating = ratings.get(player_id)
            matches_by_season = {
                season_number: match_counts.get((player_id, season_number), 0) for season_number in SEASON_NUMBERS
            }
            teams_by_season = {
                season_number: teams_by_player_season.get((player_id, season_number), [])
                for season_number in SEASON_NUMBERS
            }
            rows.append(
                PlayerExportRow(
                    player=player,
                    rating=rating.rating_points if rating else None,
                    grade=rating.grade if rating else '',
                    matches_by_season=matches_by_season,
                    teams_by_season=teams_by_season,
                    skipped_seasons=self._format_skipped_seasons(
                        matches_by_season[23],
                        matches_by_season[24],
                        last_season_by_player.get(player_id),
                    ),
                    last_season_number=last_season_by_player.get(player_id),
                )
            )

        rows.sort(key=self._sort_key)

        with open(filename, 'w', encoding='utf-8-sig', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(HEADERS)
            for row in rows:
                writer.writerow(self._build_csv_row(row, site_url))

        self.stdout.write(f'Exported {len(rows)} players to {filename}', self.style.SUCCESS)

    def _load_seasons(self) -> dict[int, Season]:
        seasons = {}
        for season_number in SEASON_NUMBERS:
            try:
                seasons[season_number] = Season.objects.get(number=season_number)
            except Season.DoesNotExist as exc:
                raise CommandError(f'Season with number={season_number} does not exist') from exc
        return seasons

    def _load_rating_version(self, rating_version_number: int | None) -> PlayerRatingVersion:
        if rating_version_number is not None:
            try:
                return PlayerRatingVersion.objects.get(number=rating_version_number)
            except PlayerRatingVersion.DoesNotExist as exc:
                raise CommandError(f'Rating version {rating_version_number} does not exist') from exc

        rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        if rating_version is None:
            raise CommandError('No player rating versions found')
        return rating_version

    def _collect_player_ids(self, rating_version: PlayerRatingVersion) -> set[int]:
        rated_player_ids = set(PlayerRating.objects.filter(version=rating_version).values_list('player_id', flat=True))
        active_player_ids = set(
            PlayerMatchStatistics.objects.filter(
                league__championship__number__in=SEASON_NUMBERS,
                match__is_played=True,
            )
            .values_list('player_id', flat=True)
            .distinct()
        )
        return rated_player_ids | active_player_ids

    def _collect_season_stats(
        self, player_ids: set[int]
    ) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], list[str]]]:
        match_counts: dict[tuple[int, int], int] = {}
        teams_by_player_season: dict[tuple[int, int], list[str]] = defaultdict(list)
        seen_teams: dict[tuple[int, int], set[str]] = defaultdict(set)

        stats_qs = (
            PlayerMatchStatistics.objects.filter(
                player_id__in=player_ids,
                league__championship__number__in=SEASON_NUMBERS,
                match__is_played=True,
            )
            .values('player_id', 'league__championship__number', 'team__title')
            .annotate(matches=Count('match', distinct=True))
            .order_by('player_id', 'league__championship__number', 'team__title')
        )

        for entry in stats_qs:
            key = (entry['player_id'], entry['league__championship__number'])
            current_match_count = match_counts.get(key, 0)
            match_counts[key] = current_match_count + entry['matches']
            team_title = entry['team__title']
            if team_title not in seen_teams[key]:
                seen_teams[key].add(team_title)
                teams_by_player_season[key].append(team_title)

        return match_counts, teams_by_player_season

    def _collect_last_seasons(self, player_ids: set[int]) -> dict[int, int]:
        return dict(
            PlayerMatchStatistics.objects.filter(
                player_id__in=player_ids,
                match__is_played=True,
            )
            .values('player_id')
            .annotate(last_season=Max('league__championship__number'))
            .values_list('player_id', 'last_season')
        )

    def _format_skipped_seasons(
        self,
        matches_season_23: int,
        matches_season_24: int,
        last_season_number: int | None,
    ) -> str:
        if matches_season_23 > 0 or matches_season_24 > 0:
            return ''

        if last_season_number is None:
            return '3+'

        skipped = (24 - last_season_number) // 2
        if skipped >= 3:
            return '3+'
        return str(skipped)

    def _sort_key(self, row: PlayerExportRow) -> tuple:
        has_skipped_season = bool(row.skipped_seasons)
        rating = row.rating if row.rating is not None else -1
        total_matches = row.matches_by_season[23] + row.matches_by_season[24]
        return (has_skipped_season, -rating, -total_matches, row.player.nickname.casefold())

    def _build_csv_row(self, row: PlayerExportRow, site_url: str) -> list:
        return [
            self._format_player_cell(row.player, site_url),
            row.rating if row.rating is not None else '',
            row.grade,
            row.matches_by_season[23],
            ';'.join(row.teams_by_season[23]),
            row.matches_by_season[24],
            ';'.join(row.teams_by_season[24]),
            row.skipped_seasons,
        ]

    def _format_player_cell(self, player: Player, site_url: str) -> str:
        profile = getattr(getattr(player, 'name', None), 'user_profile', None)
        if profile is None:
            return player.nickname

        url = f'{site_url}{profile.get_absolute_url()}'
        nickname = player.nickname.replace('"', '""')
        return f'=HYPERLINK("{url}";"{nickname}")'
