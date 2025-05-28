import csv

from core.models import UserNicknameHistoryItem
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Player, PlayerRating, PlayerRatingVersion


class Command(BaseCommand):
    help = 'Import players rating from csv file'
    
    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='path to .csv file')
        parser.add_argument('-V', dest='version', type=int, help='rating version')
        parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true')
    
    def handle(self, *args,  **options) -> str | None:
        filename = options['filename']
        version = options['version']
        
        if not version:
            last_version = PlayerRatingVersion.objects.order_by('-number').first()
            version = last_version.number + 1 if last_version else 1
            
        rating_version, created = PlayerRatingVersion.objects.get_or_create(
            number=version,
            defaults={'date': timezone.localdate()}
        )
        
        if not created:
            print(f'ERROR: Version {version} already exists')
            return
         
        rows_count = 0
        with open(filename, 'r') as file:
            reader = csv.reader(file.readlines())
            for row in reader:
                nickname, rating, grade = row
                rating = int(rating)
                player = Player.objects.filter(nickname=nickname).first()
                if not player:
                    user = UserNicknameHistoryItem.objects.filter(nickname=nickname).first()
                    if user:
                        player = user.user.user_player
                
                if not player:
                    print(f'WARN: Player {nickname} not found')
                else:
                    PlayerRating.objects.create(version=rating_version, player=player, rating_points=rating, grade=grade)
                    rows_count += 1
                
        print(f'{rows_count} entries was imported from file {filename}')
                    
