import time

from django.core.management.base import BaseCommand

from tournament.tasks import fetch_match_replay_stats

from ...models import Match


class Command(BaseCommand):
    help = 'Build match stats'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        matches = Match.objects.filter(league__championship__number=22)
        for match in matches:
            if match.id == 6124:
                fetch_match_replay_stats.delay(match.id)
                time.sleep(5)
        print(f'{len(matches)} matches will be processed')
