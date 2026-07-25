from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournament.models import Card, CleanSheet, Goal, Match, OtherEvents, PlayerMatchStatistics


class Command(BaseCommand):
    help = 'Copy legacy OtherEvents into dedicated domain models without changing match scores'

    MODES = ('own-goals', 'cards', 'clean-sheets', 'all')

    def add_arguments(self, parser):
        parser.add_argument('--mode', choices=self.MODES, default='own-goals')
        parser.add_argument('--dry-run', action='store_true', help='Validate and report without creating objects')
        parser.add_argument('--verify-only', action='store_true', help='Verify an already completed migration')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['dry_run'] and options['verify_only']:
            raise CommandError('--dry-run and --verify-only cannot be used together')

        mode = options['mode']
        selected_modes = self.MODES[:-1] if mode == 'all' else (mode,)
        source_match_ids = set()
        source_querysets = {
            'own-goals': OtherEvents.objects.ogs(),
            'cards': OtherEvents.objects.cards(),
            'clean-sheets': OtherEvents.objects.cs(),
        }
        for selected_mode in selected_modes:
            source_match_ids.update(source_querysets[selected_mode].values_list('match_id', flat=True))

        scores_before = self._scores(source_match_ids)
        for selected_mode in selected_modes:
            if selected_mode == 'own-goals':
                self._migrate_own_goals(options)
            elif selected_mode == 'cards':
                self._migrate_cards(options)
            else:
                self._migrate_clean_sheets(options)

        if scores_before != self._scores(source_match_ids):
            raise CommandError('match scores changed while migrating legacy events')

    def _migrate_own_goals(self, options):
        source_events = list(OtherEvents.objects.ogs().select_related('match', 'team', 'author').order_by('pk'))
        migrated_by_event = {
            goal.legacy_event_id: goal
            for goal in Goal.objects.own_goals()
            .filter(legacy_event_id__in=[event.pk for event in source_events])
            .select_related('match')
        }
        participant_pairs = self._participant_pairs(source_events)
        errors = []
        warnings = []
        objects_to_create = []

        for event in source_events:
            if not self._has_required_fields(event, errors):
                continue
            if event.team_id == event.match.team_home_id:
                credited_team_id = event.match.team_guest_id
            elif event.team_id == event.match.team_guest_id:
                credited_team_id = event.match.team_home_id
            else:
                errors.append(f'event {event.pk}: team is not a match participant')
                continue

            self._append_participant_warning(event, participant_pairs, warnings)
            values = {
                'match_id': event.match_id,
                'team_id': credited_team_id,
                'own_goal_team_id': event.team_id,
                'own_goal_author_id': event.author_id,
                'time_min': event.time_min,
                'time_sec': event.time_sec,
            }
            existing = migrated_by_event.get(event.pk)
            if existing:
                self._check_existing(event.pk, existing, values, errors)
                continue

            objects_to_create.append(
                Goal(
                    **values,
                    kind=Goal.Kind.OWN_GOAL,
                    author_id=None,
                    assistent_id=None,
                    legacy_event_id=event.pk,
                )
            )

        self._finish_mode(
            'own-goals', source_events, migrated_by_event, objects_to_create, Goal, errors, warnings, options
        )

    def _migrate_cards(self, options):
        source_events = list(OtherEvents.objects.cards().select_related('match', 'team', 'author').order_by('pk'))
        migrated_by_event = {
            card.legacy_event_id: card
            for card in Card.objects.filter(legacy_event_id__in=[event.pk for event in source_events])
        }
        participant_pairs = self._participant_pairs(source_events)
        errors = []
        warnings = []
        objects_to_create = []

        for event in source_events:
            if not self._has_required_fields(event, errors):
                continue
            self._append_event_warnings(event, participant_pairs, warnings)
            values = {
                'match_id': event.match_id,
                'team_id': event.team_id,
                'author_id': event.author_id,
                'kind': event.event,
                'time_min': event.time_min,
                'time_sec': event.time_sec,
                'reason': event.card_reason or '',
            }
            existing = migrated_by_event.get(event.pk)
            if existing:
                self._check_existing(event.pk, existing, values, errors)
                continue
            objects_to_create.append(Card(**values, legacy_event_id=event.pk))

        self._finish_mode('cards', source_events, migrated_by_event, objects_to_create, Card, errors, warnings, options)

    def _migrate_clean_sheets(self, options):
        source_events = list(OtherEvents.objects.cs().select_related('match', 'team', 'author').order_by('pk'))
        migrated_by_event = {
            clean_sheet.legacy_event_id: clean_sheet
            for clean_sheet in CleanSheet.objects.filter(legacy_event_id__in=[event.pk for event in source_events])
        }
        participant_pairs = self._participant_pairs(source_events)
        errors = []
        warnings = []
        objects_to_create = []

        for event in source_events:
            if not self._has_required_fields(event, errors):
                continue
            self._append_event_warnings(event, participant_pairs, warnings)
            period = self._clean_sheet_period(event)
            if period == CleanSheet.Period.EXTRA_TIME and event.match.duration.total_seconds() <= 16 * 60:
                warnings.append(
                    f'event {event.pk} [match {event.match_id}]: extra-time clean sheet belongs to a match '
                    'whose duration is not greater than 16 minutes'
                )
            values = {
                'match_id': event.match_id,
                'team_id': event.team_id,
                'author_id': event.author_id,
                'period': period,
            }
            existing = migrated_by_event.get(event.pk)
            if existing:
                self._check_existing(event.pk, existing, values, errors)
                continue
            objects_to_create.append(CleanSheet(**values, legacy_event_id=event.pk))

        self._finish_mode(
            'clean-sheets',
            source_events,
            migrated_by_event,
            objects_to_create,
            CleanSheet,
            errors,
            warnings,
            options,
        )

    def _finish_mode(
        self,
        mode,
        source_events,
        migrated_by_event,
        objects_to_create,
        model,
        errors,
        warnings,
        options,
    ):
        for warning in warnings:
            self.stdout.write(self.style.WARNING(warning))
        if errors:
            raise CommandError('\n'.join(errors))
        if options['verify_only'] and objects_to_create:
            raise CommandError(f'{len(objects_to_create)} legacy {mode} events have not been migrated')

        if not options['dry_run'] and not options['verify_only']:
            model.objects.bulk_create(objects_to_create)

        migrated_count = len(migrated_by_event)
        if not options['dry_run'] and not options['verify_only']:
            migrated_count += len(objects_to_create)
        if (options['verify_only'] or not options['dry_run']) and migrated_count != len(source_events):
            raise CommandError(
                f'{mode}: migrated count {migrated_count} does not match source count {len(source_events)}'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'mode={mode} source={len(source_events)} '
                f'created={0 if options["dry_run"] or options["verify_only"] else len(objects_to_create)} '
                f'skipped={len(source_events) - len(objects_to_create)} warnings={len(warnings)}'
            )
        )

    @staticmethod
    def _has_required_fields(event, errors):
        if not event.match_id or not event.team_id or not event.author_id:
            errors.append(f'event {event.pk}: missing match, team, or author')
            return False
        return True

    @staticmethod
    def _participant_pairs(events):
        return set(
            PlayerMatchStatistics.objects.filter(match_id__in={event.match_id for event in events}).values_list(
                'match_id', 'player_id', 'team_id'
            )
        )

    @staticmethod
    def _append_participant_warning(event, participant_pairs, warnings):
        if (event.match_id, event.author_id, event.team_id) not in participant_pairs:
            warnings.append(
                f'event {event.pk} [match {event.match_id}]: author {event.author_id} is not recorded for team '
                f'{event.team_id} in PlayerMatchStatistics'
            )

    def _append_event_warnings(self, event, participant_pairs, warnings):
        if event.team_id not in (event.match.team_home_id, event.match.team_guest_id):
            warnings.append(
                f'event {event.pk} [match {event.match_id}]: team {event.team_id} '
                'is not a match participant; copied unchanged'
            )
        self._append_participant_warning(event, participant_pairs, warnings)

    @staticmethod
    def _check_existing(event_id, existing, expected, errors):
        changed = {
            field: (getattr(existing, field), value)
            for field, value in expected.items()
            if getattr(existing, field) != value
        }
        if changed:
            errors.append(f'event {event_id}: migrated object differs: {changed}')

    @staticmethod
    def _clean_sheet_period(event):
        timestamp = event.time_min * 60 + event.time_sec
        if timestamp <= 8 * 60 + 1:
            return CleanSheet.Period.FIRST_HALF
        if timestamp <= 16 * 60 + 1:
            return CleanSheet.Period.SECOND_HALF
        return CleanSheet.Period.EXTRA_TIME

    @staticmethod
    def _scores(match_ids):
        return {
            match_id: scores
            for match_id, *scores in Match.objects.filter(pk__in=match_ids).values_list(
                'pk', 'score_home', 'score_guest'
            )
        }
