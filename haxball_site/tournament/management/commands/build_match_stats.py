from django.core.management.base import BaseCommand

from tournament.tasks import fetch_match_replay_stats

from ...models import Match


class Command(BaseCommand):
    help = 'Build match stats'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=None,
            help='Season number (championship.number) to filter matches',
        )
        parser.add_argument(
            '--match-ids',
            type=int,
            nargs='+',
            default=None,
            help='List of match IDs to process',
        )

    def handle(self, *args, **options):
        season_number = options.get('season')
        match_ids = options.get('match_ids')

        matches = Match.objects.all().order_by('id')
        if season_number is not None:
            matches = matches.filter(league__championship__number=season_number)
        if match_ids:
            matches = matches.filter(id__in=match_ids)

        self.stdout.write(f'{matches.count()} matches will be processed')
        for match in matches:
            fetch_match_replay_stats.delay(match.id)
