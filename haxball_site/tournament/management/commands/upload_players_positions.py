import csv

from django.core.management.base import BaseCommand

from core.models import UserNicknameHistoryItem
from tournament.models import Player


class Command(BaseCommand):
    help = 'Upload and update players positions from a csv file. CSV columns: nickname, position1, position2 (optional)'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='path to .csv file')
        parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true')
        parser.add_argument(
            '--reset', dest='reset', action='store_true', help='Remove all player positions before setting new ones'
        )

    def handle(self, *args, **options):
        filename = options['filename']
        dry_run = options['dry_run']
        reset = options['reset']
        updated = 0
        not_found = 0

        # Reset all player positions if --reset option is used
        if reset:
            if not dry_run:
                reset_count = Player.objects.exclude(positions__isnull=True).exclude(positions=[]).update(positions=[])
                self.stdout.write(self.style.SUCCESS(f'Reset positions for {reset_count} players'))
            else:
                reset_count = Player.objects.exclude(positions__isnull=True).exclude(positions=[]).count()
                self.stdout.write(self.style.WARNING(f'DRY RUN: Would reset positions for {reset_count} players'))
        with open(filename, 'r') as file:
            reader = csv.reader(file.readlines())
            for row in reader:
                if not row or len(row) < 2:
                    continue
                nickname = row[0].strip()
                position1 = row[1].strip() if len(row) > 1 else None
                position2 = row[2].strip() if len(row) > 2 else None
                player = Player.objects.filter(nickname=nickname).first()
                if not player:
                    not_found += 1
                    history_item = UserNicknameHistoryItem.objects.filter(nickname=nickname).first()
                    if not history_item:
                        self.stdout.write(self.style.WARNING(f'Player {nickname} not found'))
                        continue

                    player = history_item.user.user_player
                    self.stdout.write(self.style.WARNING(f'Player {nickname} not found, current nickname: {player}'))
                    continue
                self.stdout.write(self.style.SUCCESS(f'Player {nickname} found: {player}'))
                positions = []
                if position1:
                    positions.append(position1)
                if position2:
                    positions.append(position2)
                if not dry_run:
                    player.positions = positions or None
                    player.save(update_fields=['positions'])
                self.stdout.write(self.style.SUCCESS(f'Updated {nickname}: positions={positions}'))
                updated += 1
        self.stdout.write(self.style.SUCCESS(f'Updated {updated} players. Not found: {not_found}'))
