import datetime
import random

from django.core.management.base import BaseCommand

from ...models import League, TourNumber, Match

class Command(BaseCommand):
    help = 'The Zen of Python'
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
        parser.add_argument('-r', dest='has_return_matches', action='store_true')

    def handle(self, *args, **options):
        has_return_matches = options['has_return_matches']
        tournament_title = options['tournament']
        league = League.objects.get(title=tournament_title, championship__is_active=True)

        teams = list(league.teams.all())
        # add dummy team when number of teams is odd
        if len(teams) % 2 == 1:
            teams.append(None)
        half = len(teams) // 2
        n = len(teams)

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
            (tour_date_start, tour_date_end) = self.tour_dates[i]
            tour = TourNumber.objects.create(number=tour_number, league=league,
                                             date_from=tour_date_start, date_to=tour_date_end)
            if has_return_matches:
                reverse_tour_number = n + i - 1
                (tour_date_start, tour_date_end) = self.tour_dates[reverse_tour_number]
                tour_reverse = TourNumber.objects.create(number=reverse_tour_number, league=league,
                                                         date_from=tour_date_start, date_to=tour_date_end)
            print(f'                 Тур {tour}')
            for j in range(half):
                team_home = teams[j]
                team_guest = teams[n - j - 1]
                # skip matches with dummy team
                if team_home is None or team_guest is None:
                    continue
                # switch home/away for fixed (first) team
                if j == 0 and i % 2 == 1:
                    (team_home, team_guest) = (team_guest, team_home)
                match = Match.objects.create(team_home=team_home, team_guest=team_guest, numb_tour=tour, league=league)
                if has_return_matches:
                    match_reverse = Match.objects.create(team_guest=team_home, team_home=team_guest,
                                                         numb_tour=tour_reverse, league=league)
                print(f'          {match.team_home.title} - {match.team_guest.title}')

            # rotate teams n // 2 times
            for j in range(half):
                teams.insert(1, teams.pop())

        print()
        print('     Генерация расписания завершена')