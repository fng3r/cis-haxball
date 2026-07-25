from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournament.models import Goal, Match, OtherEvents, PlayerMatchStatistics


class Command(BaseCommand):
    help = 'Copy legacy own-goal events into Goal without changing match scores'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Validate and report without creating goals')
        parser.add_argument('--verify-only', action='store_true', help='Verify an already completed migration')

    @transaction.atomic
    def handle(self, *args, **options):
        source_events = list(OtherEvents.objects.ogs().select_related('match', 'team', 'author').order_by('pk'))
        source_ids = [event.pk for event in source_events]
        migrated = Goal.objects.own_goals().filter(legacy_event_id__in=source_ids)
        migrated_by_event = {goal.legacy_event_id: goal for goal in migrated.select_related('match')}

        structural_errors = []
        participant_warnings = []
        goals_to_create = []

        participant_pairs = set(
            PlayerMatchStatistics.objects.filter(match_id__in={event.match_id for event in source_events}).values_list(
                'match_id', 'player_id', 'team_id'
            )
        )

        for event in source_events:
            if not event.match_id or not event.team_id or not event.author_id:
                structural_errors.append(f'event {event.pk}: missing match, team, or author')
                continue

            match = event.match
            if event.team_id == match.team_home_id:
                credited_team_id = match.team_guest_id
            elif event.team_id == match.team_guest_id:
                credited_team_id = match.team_home_id
            else:
                structural_errors.append(f'event {event.pk}: team is not a match participant')
                continue

            if (event.match_id, event.author_id, event.team_id) not in participant_pairs:
                participant_warnings.append(
                    f'event {event.pk}: author {event.author_id} is not recorded for team '
                    f'{event.team_id} in PlayerMatchStatistics'
                )

            existing = migrated_by_event.get(event.pk)
            if existing:
                mismatches = {
                    'match_id': (existing.match_id, event.match_id),
                    'team_id': (existing.team_id, credited_team_id),
                    'own_goal_team_id': (existing.own_goal_team_id, event.team_id),
                    'own_goal_author_id': (existing.own_goal_author_id, event.author_id),
                    'time_min': (existing.time_min, event.time_min),
                    'time_sec': (existing.time_sec, event.time_sec),
                }
                changed = {field: values for field, values in mismatches.items() if values[0] != values[1]}
                if changed:
                    structural_errors.append(f'event {event.pk}: migrated goal differs: {changed}')
                continue

            goals_to_create.append(
                Goal(
                    match_id=event.match_id,
                    kind=Goal.Kind.OWN_GOAL,
                    team_id=credited_team_id,
                    own_goal_team_id=event.team_id,
                    own_goal_author_id=event.author_id,
                    author_id=None,
                    assistent_id=None,
                    time_min=event.time_min,
                    time_sec=event.time_sec,
                    legacy_event_id=event.pk,
                )
            )

        for warning in participant_warnings:
            self.stdout.write(self.style.WARNING(warning))

        if structural_errors:
            raise CommandError('\n'.join(structural_errors))

        if options['verify_only'] and goals_to_create:
            raise CommandError(f'{len(goals_to_create)} legacy own goals have not been migrated')

        affected_matches = {event.match_id for event in source_events}
        scores_before = {
            match_id: scores
            for match_id, *scores in Match.objects.filter(pk__in=affected_matches).values_list(
                'pk', 'score_home', 'score_guest'
            )
        }

        if not options['dry_run'] and not options['verify_only']:
            Goal.objects.bulk_create(goals_to_create)

        scores_after = {
            match_id: scores
            for match_id, *scores in Match.objects.filter(pk__in=affected_matches).values_list(
                'pk', 'score_home', 'score_guest'
            )
        }
        if scores_before != scores_after:
            raise CommandError('match scores changed while migrating own goals')

        migrated_count = len(migrated_by_event)
        if not options['dry_run'] and not options['verify_only']:
            migrated_count += len(goals_to_create)
        if (options['verify_only'] or not options['dry_run']) and migrated_count != len(source_events):
            raise CommandError(
                f'migrated own-goal count {migrated_count} does not match source count {len(source_events)}'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'source={len(source_events)} created={0 if options["dry_run"] else len(goals_to_create)} '
                f'skipped={len(source_events) - len(goals_to_create)} '
                f'warnings={len(participant_warnings)}'
            )
        )
