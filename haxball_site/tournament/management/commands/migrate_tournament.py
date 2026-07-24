import textwrap

from django.core.management.base import BaseCommand

from ...models import (
    Group,
    GroupStage,
    League,
    PlayOffStage,
    PostponementSlots,
    RegularStage,
    TourNumber,
)


class Command(BaseCommand):
    help = 'Generate schedule using round-robin algorythm'

    def add_arguments(self, parser):
        parser.add_argument('old_tournament', type=str)
        parser.add_argument('new_tournament', type=str)
        parser.add_argument('-n', dest='season_number', required=True, type=int)
        parser.add_argument('-s', '--slug', type=str)
        parser.add_argument('-o', dest='stage_order', default=1, type=int)
        parser.add_argument('-g', '--group', type=str)

    def handle(self, *args, **options):
        old_tournament_title = options['old_tournament']
        new_tournament_title = options['new_tournament']
        season_number = options['season_number']
        slug = options['slug']
        group_title = options['group']
        stage_order = options['stage_order']

        old_league = (
            League.objects.filter(title=old_tournament_title, championship__number=season_number)
            .order_by('created')
            .first()
        )
        print(f'Migrating "{old_league}" to the new format":')
        wrapper = textwrap.TextWrapper(width=100, initial_indent='  - ', subsequent_indent=' ' * 4)

        new_slug = slug or f'{old_league.slug}_v2'
        new_league, _ = League.objects.get_or_create(
            title=new_tournament_title,
            championship=old_league.championship,
            slug=new_slug,
            defaults={
                'type': old_league.type,
                'priority': old_league.priority,
                'commentable': old_league.commentable,
            },
        )
        if season_number >= 15:
            PostponementSlots.objects.get_or_create(
                league=new_league,
                defaults={
                    'common_count': old_league.postponement_slots.common_count,
                    'emergency_count': old_league.postponement_slots.emergency_count,
                    'extra_count': old_league.postponement_slots.extra_count,
                },
            )

        teams_count = old_league.teams.count()
        new_league.teams.add(*old_league.teams.all())
        print(wrapper.fill(f'{teams_count} teams were added to a new tournament'))

        group = None
        if old_league.is_cup:
            stage, _ = PlayOffStage.objects.get_or_create(league=new_league, defaults={'order': stage_order})
        elif group_title:
            stage, _ = GroupStage.objects.get_or_create(league=new_league, defaults={'order': stage_order})
            group, _ = Group.objects.get_or_create(stage=stage, name=group_title)
            group.teams.set(old_league.teams.all())
        else:
            stage, _ = RegularStage.objects.get_or_create(league=new_league, defaults={'order': stage_order})

        stage.teams.add(*old_league.teams.all())

        tours_count = old_league.tours.count()
        print(wrapper.fill(f'Discovered {tours_count} tours'))
        matches_count = 0
        for tour in old_league.tours.all():
            new_tour, _ = TourNumber.objects.get_or_create(
                league=new_league, stage=stage, number=tour.number, date_from=tour.date_from, date_to=tour.date_to
            )
            new_tour.disqualifications.add(*tour.disqualifications.all())
            new_tour.lifted_disqualifications.add(*tour.lifted_disqualifications.all())
            tour.disqualifications.clear()
            tour.lifted_disqualifications.clear()

            for match in tour.tour_matches.all():
                match.league = new_league
                match.stage = stage
                match.group = group
                match.numb_tour = new_tour
                match.save(update_fields=['league', 'stage', 'group', 'numb_tour'])
                matches_count += 1
        print(wrapper.fill(f'{tours_count} tours were created successfully, tour disqualifications were transferred'))
        print(wrapper.fill(f'{matches_count} matches were transferred'))

        comments_count = old_league.comments.count()
        print(wrapper.fill(f'Discovered {comments_count} comments'))
        for comment in old_league.comments.all():
            comment.object_id = new_league.id
            comment.save(update_fields=['object_id'])
        print(wrapper.fill(f'{comments_count} comments were transferred successfully'))
