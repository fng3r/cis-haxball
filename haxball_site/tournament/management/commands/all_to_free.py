from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from ...models import Player, PlayerTransfer, Season


class Command(BaseCommand):
    help = 'Всех в СА'

    def add_arguments(self, parser):
        parser.add_argument(
            'season',
            default=0,
            nargs='?',
            type=int,
        )

    def handle(self, *args, **options):
        print(f'season arg={options["season"]}')
        try:
            season = Season.objects.get(number=options['season'])
        except:
            season = Season.objects.filter(is_active=True).get()

        players_in_team = Player.objects.filter(~Q(team=None))

        print(f'Season {season.title} was selected as a season for all transfers')
        for player in players_in_team:
            print(f'{player}: {player.team} -> Free Agent')
            PlayerTransfer.objects.create(
                trans_player=player,
                from_team=player.team,
                to_team=None,
                season_join=season,
                date_join=timezone.now(),
                is_technical=True,
            )

        print('All players are free agents now!')
