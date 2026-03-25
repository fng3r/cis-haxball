from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from tournament.models import League, MatchReplayStatsPlayer


@dataclass
class AggregatedPlayerStats:
    name: str
    shots_total: int = 0
    shots_on_target: int = 0
    passes_completed: int = 0
    pass_attempts: int = 0
    saves: int = 0
    touches: int = 0

    @property
    def pass_completion_rate(self) -> float:
        if not self.pass_attempts:
            return 0.0
        return 100 * self.passes_completed / self.pass_attempts


class Command(BaseCommand):
    help = 'Show top replay-based player stats for a specific league'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tournament',
            type=str,
            required=True,
            help='League slug to aggregate replay player stats for',
        )
        parser.add_argument(
            '--top',
            type=int,
            default=5,
            help='Number of players to display in each leaderboard',
        )

    def handle(self, *args, **options):
        tournament_slug = options['tournament']
        top_n = options['top']
        if top_n <= 0:
            raise CommandError('--top must be a positive integer')

        league = League.objects.filter(slug=tournament_slug).first()
        if league is None:
            raise CommandError(f'League with slug="{tournament_slug}" does not exist')

        queryset = (
            MatchReplayStatsPlayer.objects.filter(replay_stats__match__league=league)
            .select_related('player')
            .order_by('id')
        )

        players: dict[tuple[str, int | str], AggregatedPlayerStats] = {}
        for entry in queryset.iterator(chunk_size=1000):
            if entry.player_id:
                key = ('player', entry.player_id)
                display_name = entry.player.nickname
            else:
                replay_nick = (entry.nick or '').strip() or '—'
                key = ('nick', replay_nick.casefold())
                display_name = replay_nick

            if key not in players:
                players[key] = AggregatedPlayerStats(name=display_name)

            acc = players[key]
            acc.shots_total += entry.shots_total
            acc.shots_on_target += entry.shots_on_target
            acc.passes_completed += entry.passes_completed
            acc.pass_attempts += entry.pass_attempts
            acc.saves += entry.saves
            acc.touches += entry.touches

        if not players:
            self.stdout.write(f'No replay player stats found for league "{league.title}" ({league.id})')
            return

        aggregated = list(players.values())
        self.stdout.write(f'League: {league.title}')
        self.stdout.write(f'Players aggregated: {len(aggregated)}')
        self.stdout.write('')

        self._write_table(
            title='Top by Total Shots',
            rows=sorted(aggregated, key=lambda player: (-player.shots_total, player.name.casefold()))[:top_n],
            value_header='Shots',
            value_getter=lambda player: str(player.shots_total),
        )
        self._write_table(
            title='Top by Shots on Target',
            rows=sorted(aggregated, key=lambda player: (-player.shots_on_target, player.name.casefold()))[:top_n],
            value_header='On target',
            value_getter=lambda player: str(player.shots_on_target),
        )
        self._write_table(
            title='Top by Completed Passes',
            rows=sorted(aggregated, key=lambda player: (-player.passes_completed, player.name.casefold()))[:top_n],
            value_header='Passes',
            value_getter=lambda player: str(player.passes_completed),
        )

        pass_accuracy_candidates = [player for player in aggregated if player.passes_completed >= 50]
        self._write_table(
            title='Top by Pass Completion Rate (min 50 completed passes)',
            rows=sorted(
                pass_accuracy_candidates,
                key=lambda player: (-player.pass_completion_rate, -player.passes_completed, player.name.casefold()),
            )[:top_n],
            value_header='Accuracy',
            value_getter=(
                lambda player: f'{player.pass_completion_rate:.1f}%'
                + f'({player.passes_completed}/{player.pass_attempts})'
            ),
        )
        self._write_table(
            title='Top by Saves',
            rows=sorted(aggregated, key=lambda player: (-player.saves, player.name.casefold()))[:top_n],
            value_header='Saves',
            value_getter=lambda player: str(player.saves),
        )
        self._write_table(
            title='Top by Touches',
            rows=sorted(aggregated, key=lambda player: (-player.touches, player.name.casefold()))[:top_n],
            value_header='Touches',
            value_getter=lambda player: str(player.touches),
        )

    def _write_table(self, *, title: str, rows: list[AggregatedPlayerStats], value_header: str, value_getter) -> None:
        self.stdout.write(title)
        if not rows:
            self.stdout.write('  No data')
            self.stdout.write('')
            return

        rank_width = len(str(len(rows)))
        player_width = max(len('Player'), *(len(row.name) for row in rows))
        value_width = max(len(value_header), *(len(value_getter(row)) for row in rows))

        header = f'{"#":>{rank_width}}  {"Player":<{player_width}}  {value_header:>{value_width}}'
        self.stdout.write(header)
        self.stdout.write(f'{"-" * rank_width}  {"-" * player_width}  {"-" * value_width}')

        for index, row in enumerate(rows, start=1):
            value = value_getter(row)
            self.stdout.write(f'{index:>{rank_width}}  {row.name:<{player_width}}  {value:>{value_width}}')

        self.stdout.write('')
