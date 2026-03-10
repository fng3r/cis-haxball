from collections import defaultdict

from django.core.management.base import BaseCommand

from tournament.models import MatchReplayStatsPlayer


class Command(BaseCommand):
    help = 'Print matches where replay player stats contain suspicious player entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            choices=['zero-playtime', 'no-player'],
            default='zero-playtime',
            help='Diagnostic mode: zero-playtime players or stats entries with no resolved player',
        )
        parser.add_argument(
            '--match-ids',
            type=int,
            nargs='+',
            default=None,
            help='Optional list of match IDs to limit the scan',
        )
        parser.add_argument(
            '--season',
            type=int,
            default=None,
            help='Optional season number to limit matches by league championship season',
        )

    def handle(self, *args, **options):
        mode = options.get('mode')
        match_ids = options.get('match_ids')
        season = options.get('season')

        if mode == 'zero-playtime':
            target_qs = MatchReplayStatsPlayer.objects.filter(played_ticks=0)
            empty_message = 'No matches with zero-playtime players found'
        else:
            target_qs = MatchReplayStatsPlayer.objects.filter(player__isnull=True)
            empty_message = 'No matches with players missing player relation found'

        target_qs = target_qs.select_related('replay_stats__match')
        if match_ids:
            target_qs = target_qs.filter(replay_stats__match_id__in=match_ids)
        if season is not None:
            target_qs = target_qs.filter(replay_stats__match__league__championship__number=season)

        matches_to_players: dict[int, set[str]] = defaultdict(set)
        for entry in target_qs.order_by('replay_stats__match_id', 'nick'):
            matches_to_players[entry.replay_stats.match_id].add(entry.nick)

        if not matches_to_players:
            self.stdout.write(empty_message)
            return

        for match_id in sorted(matches_to_players):
            players = ', '.join(sorted(matches_to_players[match_id]))
            self.stdout.write(f'{match_id}: {players}')

        total_matches = len(matches_to_players)
        if mode == 'zero-playtime':
            self.stdout.write(f'Total matches with zero-playtime players: {total_matches}')
        else:
            self.stdout.write(f'Total matches with missing player relation: {total_matches}')
