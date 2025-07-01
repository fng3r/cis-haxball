from django.core.management.base import BaseCommand, CommandError

from ...models import Match, Season


class Command(BaseCommand):
    help = 'Считаем активность инспекторов'

    def add_arguments(self, parser):
        parser.add_argument(
            'champ_number',
            default=0,
            nargs='?',
            type=int,
        )

    def handle(self, *args, **options):
        print(options['champ_number'])
        if options['champ_number'] == 0:
            print('Выборка по всем сезонам')
            all_matches = Match.objects.filter(is_played=True)
        else:
            try:
                season = Season.objects.get(number=options['champ_number'])
            except:
                raise CommandError('Выбран несуществующий сезон')

            print(f'Выборка по сезону {season.short_title}')
            all_matches = Match.objects.filter(league__championship=season, is_played=True)
        inspectors = {}
        all_events = 0
        for m in all_matches:
            all_events += (
                m.match_goal.count()
                + m.match_substitutions.count()
                + m.match_event.count()
                + m.disqualifications.count()
            )
            if m.inspector in inspectors:
                inspectors[m.inspector].append(m)
            else:
                inspectors[m.inspector] = []
                inspectors[m.inspector].append(m)

        print(f'{"Инспектор":>9} {"Матчи":>5} {"Процент матчей":>14} {"Действия":>8} {"Процент действий":>16}')
        for inspector in inspectors:
            events_added = 0
            matches = len(inspectors[inspector])
            for m in inspectors[inspector]:
                events_added += (
                    m.match_goal.count()
                    + m.match_substitutions.count()
                    + m.match_event.count()
                    + m.disqualifications.count()
                )
            matches_percent = round(100 * (matches / len(all_matches)), 1)
            events_percent = round(100 * (events_added / all_events), 1)
            inspector_username = inspector.username if inspector else '-'
            print(f'{inspector_username:<9} {matches:<5} {matches_percent:<14} {events_added:<8} {events_percent:<16}')
