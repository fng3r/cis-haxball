from time import monotonic

from django.core.management.base import BaseCommand, CommandError

from tournament.models import ReplayRecording
from tournament.services.replay_storage import recording_bytes


class Command(BaseCommand):
    help = 'Download and store existing replay files without rebuilding statistics'

    def add_arguments(self, parser):
        parser.add_argument('--season', type=int, help='Season number (championship.number)')
        parser.add_argument('--match-ids', type=int, nargs='+')

    def handle(self, *args, **options):
        recordings = ReplayRecording.objects.defer('raw_response').order_by('pk')
        if options['season'] is not None:
            recordings = recordings.filter(match__league__championship__number=options['season'])
        if options['match_ids']:
            recordings = recordings.filter(match_id__in=options['match_ids'])
        total = recordings.count()
        started = monotonic()
        self.stdout.write(f'Storing replay files for {total} recordings...')
        self.stdout.flush()
        available = downloaded = failed = 0
        for index, recording in enumerate(recordings.iterator(chunk_size=100), start=1):
            prefix = f'[{index}/{total}] Match {recording.match_id}, recording {recording.pk}'
            item_started = monotonic()
            try:
                stored = bool(recording.replay_file) and recording.replay_file.storage.exists(
                    recording.replay_file.name
                )
                action = 'Checking stored file' if stored else 'Downloading replay'
                self.stdout.write(f'{prefix}: {action}...')
                self.stdout.flush()
                data = recording_bytes(recording)
                if stored:
                    available += 1
                else:
                    downloaded += 1
                result = 'Already stored' if stored else 'Downloaded and stored'
                self.stdout.write(f'{prefix}: {result} ({len(data):,} bytes, {monotonic() - item_started:.1f}s)')
                self.stdout.flush()
            except Exception as exc:
                failed += 1
                self.stderr.write(f'{prefix}: Failed ({monotonic() - item_started:.1f}s): {exc}')
                self.stderr.flush()
        self.stdout.write(
            f'Finished in {monotonic() - started:.1f}s. '
            f'Downloaded and stored: {downloaded}; already stored: {available}; failed: {failed}'
        )
        self.stdout.flush()
        if failed:
            raise CommandError(f'Could not store {failed} recordings; rerun to retry')
