from django.core.management.base import BaseCommand, CommandError

from ...models import GroupStage, League, TournamentStage


def parse_tours_spec(raw):
    """Parse '16-22' / '16,17,19-21' into a sorted set of tour numbers."""
    numbers = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start_raw, end_raw = part.split('-', 1)
                start, end = int(start_raw), int(end_raw)
            except ValueError as exc:
                raise CommandError(f'Invalid tour range "{part}": expected like "16-22"') from exc
            if start > end:
                raise CommandError(f'Invalid tour range "{part}": start is greater than end')
            numbers.update(range(start, end + 1))
        else:
            try:
                numbers.add(int(part))
            except ValueError as exc:
                raise CommandError(f'Invalid tour number "{part}"') from exc
    if not numbers:
        raise CommandError('No tours specified')
    return numbers


class Command(BaseCommand):
    help = (
        'Move a set of tours (with their matches) from one stage to another within the same league. '
        'Used to split an existing single-stage tournament into a league-split format '
        '(e.g. move tours 16-22 of ЧР#6 into a new second stage).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--league', required=True, help='League id or slug')
        parser.add_argument('--from-stage', required=True, type=int, help='Order of the source stage')
        parser.add_argument('--to-stage', required=True, type=int, help='Order of the destination stage')
        parser.add_argument('--tours', required=True, help='Tour numbers to move, e.g. "16-22" or "16,17,19-21"')
        parser.add_argument('--dry-run', action='store_true', help='Print planned moves without saving')

    def handle(self, *args, **options):
        league_ref = options['league']
        try:
            league_id = int(league_ref)
            league = League.objects.get(pk=league_id)
        except ValueError:
            league = League.objects.filter(slug=league_ref).first()
            if league is None:
                raise CommandError(f'League "{league_ref}" not found')
        except League.DoesNotExist as exc:
            raise CommandError(f'League "{league_ref}" not found') from exc

        try:
            source = TournamentStage.objects.get(league=league, order=options['from_stage'])
        except TournamentStage.DoesNotExist as exc:
            raise CommandError(f'Source stage with order {options["from_stage"]} not found') from exc
        try:
            dest = TournamentStage.objects.get(league=league, order=options['to_stage'])
        except TournamentStage.DoesNotExist as exc:
            raise CommandError(f'Destination stage with order {options["to_stage"]} not found') from exc

        if source.id == dest.id:
            raise CommandError('Source and destination stages are the same')

        tour_numbers = parse_tours_spec(options['tours'])
        tours = list(source.tours.filter(number__in=tour_numbers).order_by('number').prefetch_related('tour_matches'))
        found_numbers = {tour.number for tour in tours}
        missing = sorted(tour_numbers - found_numbers)
        if missing:
            raise CommandError(f'Tours not found in source stage: {missing}')

        dest_is_groups = isinstance(dest, GroupStage) or dest.type == TournamentStage.StageType.GROUPS
        groups_by_team_id = {}
        if dest_is_groups:
            for group in dest.groups.prefetch_related('teams'):
                for team in group.teams.all():
                    groups_by_team_id.setdefault(team.id, []).append(group)
            if not groups_by_team_id:
                self.stdout.write(
                    self.style.WARNING(
                        'Destination group stage has no groups/teams yet: matches will be moved '
                        'without a group assigned.'
                    )
                )

        dry_run = options['dry_run']
        moved_tours = 0
        moved_matches = 0
        ungrouped = 0
        for tour in tours:
            matches = list(tour.tour_matches.all())
            self.stdout.write(f'Tour {tour.number} ({tour.date_from} – {tour.date_to}): {len(matches)} matches')
            for match in matches:
                group_info = ''
                new_group = None
                if dest_is_groups and groups_by_team_id:
                    home_groups = groups_by_team_id.get(match.team_home_id, [])
                    guest_groups = groups_by_team_id.get(match.team_guest_id, [])
                    common = [g for g in home_groups if g in guest_groups]
                    if len(common) == 1:
                        new_group = common[0]
                        group_info = f' -> group "{new_group.name}"'
                    else:
                        ungrouped += 1
                        group_info = ' -> group NOT detected (teams in different/no groups)'
                self.stdout.write(f'    {match.team_home_id}:{match.team_guest_id}{group_info}')
                if not dry_run:
                    match.stage = dest
                    match.group = new_group
                    match.save(update_fields=['stage', 'group'])
            if not dry_run:
                tour.stage = dest
                tour.save(update_fields=['stage'])
            moved_tours += 1
            moved_matches += len(matches)

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY-RUN: would move {moved_tours} tours, {moved_matches} matches.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Moved {moved_tours} tours, {moved_matches} matches.'))
            if ungrouped:
                self.stdout.write(
                    self.style.WARNING(f'{ungrouped} matches were moved without a group: assign groups manually.')
                )
