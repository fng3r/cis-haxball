from django.core.management.base import BaseCommand, CommandError

from tournament.models import ReplayRecording
from tournament.services.replay_storage import recording_bytes


class Command(BaseCommand):
    help = 'Archive existing replay files without analyzing them or changing statistics'

    def add_arguments(self, parser):
        parser.add_argument('--season', type=int, help='Season number (championship.number)')
        parser.add_argument('--match-ids', type=int, nargs='+')

    def handle(self, *args, **options):
        recordings = ReplayRecording.objects.defer('raw_response').order_by('pk')
        if options['season'] is not None:
            recordings = recordings.filter(match__league__championship__number=options['season'])
        if options['match_ids']:
            recordings = recordings.filter(match_id__in=options['match_ids'])
        archived = failed = 0
        for recording in recordings.iterator(chunk_size=100):
            try:
                recording_bytes(recording)
                archived += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(f'Recording {recording.pk}: {exc}')
        self.stdout.write(f'Available: {archived}; failed: {failed}')
        if failed:
            raise CommandError(f'Could not archive {failed} recordings; rerun to retry')
