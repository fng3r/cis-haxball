from django.core.management.base import BaseCommand, CommandError

from ...models import League, TourNumber, Match, Season


class Command(BaseCommand):
    help = 'Считаем активность инспекторов'

    def add_arguments(self, parser):
        parser.add_argument('season_number', default=0, nargs='?', type=int, )

    def handle(self, *args, **options):
        season_number = options['season_number']
        print(season_number)
        if season_number == 0:
            print('Выборка по всем сезонам')
            all_matches = Match.objects.filter(is_played=True)
        else:
            try:
                season = Season.objects.get(number=season_number)
            except:
                raise CommandError('Выбран несуществующий сезон')

            print('Выборка по сезону \'{}\''.format(season.title))
            all_matches = Match.objects.filter(league__championship=season, is_played=True)
        inspectors = {}
        events_total = 0
        for match in all_matches:
            match_events_count = (match.match_goal.count() + match.match_substitutions.count() +
                                  match.match_event.count() + match.disqualifications.count())
            events_total += match_events_count
            inspector = match.inspector
            if inspector not in inspectors:
                inspectors[inspector] = []
            inspectors[inspector].append(match)

        print('Инспектор'.ljust(15), 'Матчи    ', 'Процент матчей    ', 'Действия    ', 'Процент действий')
        for inspector in inspectors:
            events_count = 0
            for match in inspectors[inspector]:
                events_count += (match.match_goal.count() + match.match_substitutions.count() +
                                 match.match_event.count() + match.disqualifications.count())
            events_percentage = round((events_count / events_total) * 100, 1)
            matches_count = len(inspectors[inspector])
            matches_percentage = round((matches_count / all_matches.count()) * 100, 1)
            print('{:<15}'.format(str(inspector)), '{:<9}'.format(matches_count), '{:<18}'.format(matches_percentage),
                  '{:<12}'.format(events_count), '{:<20}'.format(events_percentage))
