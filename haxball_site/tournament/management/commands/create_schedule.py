import datetime
import random

from django.core.management.base import BaseCommand

from ...models import GroupStage, League, Match, RegularStage, TourNumber


class Command(BaseCommand):
    help = 'Generate schedule using round-robin algorythm'

    tour_dates = {
        1: (datetime.date(2024, 9, 1), datetime.date(2024, 9, 3)),
        2: (datetime.date(2024, 9, 1), datetime.date(2024, 9, 6)),
        3: (datetime.date(2024, 9, 4), datetime.date(2024, 9, 6)),
        4: (datetime.date(2024, 9, 8), datetime.date(2024, 9, 10)),
        5: (datetime.date(2024, 9, 11), datetime.date(2024, 9, 13)),
        6: (datetime.date(2024, 9, 15), datetime.date(2024, 9, 17)),
        7: (datetime.date(2024, 9, 15), datetime.date(2024, 9, 20)),
        8: (datetime.date(2024, 9, 18), datetime.date(2024, 9, 20)),
        9: (datetime.date(2024, 9, 22), datetime.date(2024, 9, 24)),
        10: (datetime.date(2024, 9, 25), datetime.date(2024, 9, 27)),
        11: (datetime.date(2024, 9, 29), datetime.date(2024, 10, 1)),
        12: (datetime.date(2024, 10, 6), datetime.date(2024, 10, 8)),
        13: (datetime.date(2024, 10, 9), datetime.date(2024, 10, 3)),
        14: (datetime.date(2024, 10, 13), datetime.date(2024, 10, 15)),
        15: (datetime.date(2024, 10, 13), datetime.date(2024, 10, 18)),
        16: (datetime.date(2024, 10, 16), datetime.date(2024, 10, 18)),
        17: (datetime.date(2024, 10, 20), datetime.date(2024, 10, 22)),
        18: (datetime.date(2024, 10, 23), datetime.date(2024, 10, 25)),
        19: (datetime.date(2024, 10, 27), datetime.date(2024, 10, 29)),
        20: (datetime.date(2024, 9, 30), datetime.date(2024, 11, 1)),
        21: (datetime.date(2024, 11, 3), datetime.date(2024, 11, 5)),
        22: (datetime.date(2024, 11, 6), datetime.date(2024, 11, 8)),
    }

    def add_arguments(self, parser):
        parser.add_argument('tournament', type=str)
        parser.add_argument('-s', '--stage', type=str)
        parser.add_argument('-r', dest='has_return_matches', action='store_true')

    def handle(self, *args, **options):
        has_return_matches = options['has_return_matches']
        tournament_title = options['tournament']
        stage_type = options['stage']
        league = League.objects.get(title=tournament_title, championship__is_active=True)
        stage = league.stages.filter(type=stage_type).first()

        print(league.title)
        if stage is None:
            teams = list(league.teams.all())
            self.generate_schedule(league, teams, has_return_matches)
        else:
            if isinstance(stage, RegularStage):
                teams = list(stage.teams.all())
                self.generate_schedule(league, teams, has_return_matches, stage)
            elif isinstance(stage, GroupStage):
                for group in stage.groups.all():
                    teams = list(group.teams.all())
                    self.generate_schedule(league, teams, has_return_matches, stage, group)
            else:
                raise Exception('Unknown stage type')

        print('Генерация расписания завершена')


    def generate_schedule(self, league, teams, has_return_matches, stage=None, group=None):
        # add dummy team when number of teams is odd
        if len(teams) % 2 == 1:
            teams.append(None)
        half = len(teams) // 2
        n = len(teams)

        if group:
            print(group)
        print('Список команд:')
        for team in teams:
            if team is not None:
                print(f'     {team.title}')

        print()
        print('     Перемешиваем')
        random.shuffle(teams)
        for team in teams:
            if team is not None:
                print(f'     {team.title}')

        for i in range(1, n):
            tour_number = i
            tour_start_date, tour_end_date = self.tour_dates[i]
            tour = TourNumber.objects.create(
                number=tour_number, league=league, stage=stage,
                date_from=tour_start_date, date_to=tour_end_date,
            )
            if has_return_matches:
                reversed_tour_number = n + i - 1
                tour_start_date, tour_end_date = self.tour_dates[reversed_tour_number]
                reversed_tour = TourNumber.objects.create(
                    number=reversed_tour_number, league=league, stage=stage,
                    date_from=tour_start_date, date_to=tour_end_date,
                )

            for j in range(half):
                team_home = teams[j]
                team_guest = teams[n - j - 1]

                # skip matches with dummy team
                if team_home is None or team_guest is None:
                    continue
                # switch home/away for fixed (first) team
                if j == 0 and i % 2 == 1:
                    (team_home, team_guest) = (team_guest, team_home)

                Match.objects.create(
                    team_home=team_home, team_guest=team_guest, numb_tour=tour,
                    league=league, stage=stage, group=group
                )
                if has_return_matches:
                    Match.objects.create(
                        team_guest=team_home, team_home=team_guest, numb_tour=reversed_tour,
                        league=league, stage=stage, group=group
                    )

            # rotate teams n // 2 times, first team is always fixed
            for j in range(half):
                teams.insert(1, teams.pop())

        tours = TourNumber.objects.filter(league=league, stage=stage, group=group).order_by('number')
        for tour in tours:
            print(f'             {tour.number} тур')
            for match in tour.tour_matches.all():
                print(f'     {match.team_home.title} - {match.team_guest.title}')
        print()