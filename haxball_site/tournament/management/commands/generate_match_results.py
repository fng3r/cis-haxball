import random

from PIL.ImImagePlugin import number
from django.core.management.base import BaseCommand

from ...models import League, Match, TourNumber, TournamentStage


class Command(BaseCommand):
    help = 'Generate match results in the given tournament and stage'

    def add_arguments(self, parser):
        parser.add_argument('tournament', type=str)
        parser.add_argument('-s', '--stage', type=str)
        parser.add_argument('-r', dest='has_return_matches', action='store_true')


    def handle(self, *args, **options):
        tournament_title = options['tournament']
        stage_type = options['stage']
        league = League.objects.get(title=tournament_title, championship__is_active=True)
        stage = league.stages.filter(type=stage_type).first()
        self.generate_results(stage)


    def generate_results(self, stage):
        for tour in stage.tours.all():
            for match in tour.tour_matches.all():
                is_draw = random.random() < 0.07
                home_scored = random.choice(range(1, 11))
                away_scored = home_scored if is_draw else random.choice(range(1, 11))
                match.score_home = home_scored
                match.score_guest = away_scored
                match.is_played = True
                match.save()

                print(f'{match.numb_tour}: {match.team_home} {match.score_home}-{match.score_guest} {match.team_guest}')
