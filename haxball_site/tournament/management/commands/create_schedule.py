import datetime
import json
import random
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...models import GroupStage, League, Match, RegularStage, TourNumber


class Command(BaseCommand):
    help = 'Generate schedule using round-robin algorythm'

    def add_arguments(self, parser):
        parser.add_argument('tournament', type=str)
        parser.add_argument('-s', '--stage', type=str, required=True)
        parser.add_argument('-r', dest='has_return_matches', action='store_true')
        parser.add_argument(
            '--schedule',
            type=str,
            required=True,
            help='JSON with tour dates or path to a .json file. Format: {"1": ["2026-03-07", "2026-03-09"]}',
        )

    def handle(self, *args, **options):
        has_return_matches = options['has_return_matches']
        tournament_title = options['tournament']
        stage_type = options['stage']
        tour_dates = self.parse_tour_dates(options['schedule'])
        league = League.objects.get(title=tournament_title, championship__is_active=True)
        stage = league.stages.filter(type=stage_type).first()

        print(league.title)
        if stage is None:
            raise CommandError('Stage not found')

        if isinstance(stage, RegularStage):
            teams = list(stage.teams.all())
            self.generate_schedule(league, teams, has_return_matches, stage, tour_dates=tour_dates)
        elif isinstance(stage, GroupStage):
            for group in stage.groups.all():
                teams = list(group.teams.all())
                self.generate_schedule(league, teams, has_return_matches, stage, group, tour_dates=tour_dates)
        else:
            raise CommandError('Unknown stage type')

        print('Генерация расписания завершена')

    def parse_tour_dates(self, raw_schedule):
        if Path(raw_schedule).is_file():
            with open(raw_schedule, encoding='utf-8') as schedule_file:
                raw_schedule = schedule_file.read()

        try:
            schedule = json.loads(raw_schedule)
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid schedule JSON: {exc}') from exc

        if not isinstance(schedule, dict):
            raise CommandError('Schedule must be a JSON object: {"1": ["YYYY-MM-DD", "YYYY-MM-DD"]}')

        parsed_schedule = {}
        for tour_number_raw, dates in schedule.items():
            try:
                tour_number = int(tour_number_raw)
            except (TypeError, ValueError) as exc:
                raise CommandError(f'Invalid tour number "{tour_number_raw}" in schedule') from exc

            if not isinstance(dates, list) or len(dates) != 2:
                raise CommandError(f'Invalid date range for tour {tour_number}: expected ["YYYY-MM-DD", "YYYY-MM-DD"]')

            try:
                date_from = datetime.date.fromisoformat(dates[0])
                date_to = datetime.date.fromisoformat(dates[1])
            except ValueError as exc:
                raise CommandError(f'Invalid date format for tour {tour_number}: use YYYY-MM-DD') from exc

            parsed_schedule[tour_number] = (date_from, date_to)

        return parsed_schedule

    def generate_schedule(self, league, teams, has_return_matches, stage=None, group=None, tour_dates=None):
        if tour_dates is None:
            raise CommandError('Schedule is required')
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
            try:
                tour_start_date, tour_end_date = tour_dates[i]
            except KeyError as exc:
                raise CommandError(f'Missing schedule for tour {i}') from exc
            tour = TourNumber.objects.create(
                number=tour_number,
                league=league,
                stage=stage,
                date_from=tour_start_date,
                date_to=tour_end_date,
            )
            if has_return_matches:
                reversed_tour_number = n + i - 1
                try:
                    tour_start_date, tour_end_date = tour_dates[reversed_tour_number]
                except KeyError as exc:
                    raise CommandError(f'Missing schedule for return tour {reversed_tour_number}') from exc
                reversed_tour = TourNumber.objects.create(
                    number=reversed_tour_number,
                    league=league,
                    stage=stage,
                    date_from=tour_start_date,
                    date_to=tour_end_date,
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
                    team_home=team_home, team_guest=team_guest, numb_tour=tour, league=league, stage=stage, group=group
                )
                if has_return_matches:
                    Match.objects.create(
                        team_guest=team_home,
                        team_home=team_guest,
                        numb_tour=reversed_tour,
                        league=league,
                        stage=stage,
                        group=group,
                    )

            # rotate teams n // 2 times, first team is always fixed
            for j in range(half):
                teams.insert(1, teams.pop())

        tours = TourNumber.objects.filter(league=league, stage=stage).order_by('number')
        for tour in tours:
            print(f'             {tour.number} тур')
            for match in tour.tour_matches.all():
                print(f'     {match.team_home.title} - {match.team_guest.title}')
        print()
