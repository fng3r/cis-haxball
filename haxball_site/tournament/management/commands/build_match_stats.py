from itertools import groupby

from django.core.management.base import BaseCommand, CommandError

from tournament.tasks import fetch_match_replay_stats, reanalyze_replay_recordings

from ...models import Match, ReplayRecording


class Command(BaseCommand):
    help = 'Build match stats'

    def add_arguments(self, parser):
        parser.add_argument('--reanalyze', action='store_true', help='Reanalyze even successful, unchanged recordings')
        parser.add_argument(
            '--reanalyze-all',
            action='store_true',
            help='Reanalyze every stored current recording, including recordings removed from match replay lists',
        )
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

        if options['reanalyze_all']:
            if season_number is not None or match_ids:
                raise CommandError('--reanalyze-all cannot be combined with --season or --match-ids')
            recordings = ReplayRecording.objects.order_by('match_id', 'pk').values_list('match_id', 'pk')
            self.stdout.write(f'{recordings.count()} stored recordings will be queued for reanalysis')
            recording_count = match_count = 0
            for _, group in groupby(recordings.iterator(chunk_size=500), key=lambda row: row[0]):
                recording_ids = [row[1] for row in group]
                reanalyze_replay_recordings.delay(recording_ids)
                recording_count += len(recording_ids)
                match_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'Queued reanalysis for {recording_count} recordings across {match_count} matches')
            )
            return

        matches = Match.objects.all().order_by('id')
        if season_number is not None:
            matches = matches.filter(league__championship__number=season_number)
        if match_ids:
            matches = matches.filter(id__in=match_ids)

        self.stdout.write(f'{matches.count()} matches will be processed')
        for match in matches:
            fetch_match_replay_stats.delay(match.id, force=options['reanalyze'])
