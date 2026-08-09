from collections import defaultdict
from typing import Callable

from django.core.management.base import CommandError
from django.db.models import Q
from django.db.models.functions import Coalesce

from tournament.models import Medal, MedalType, Player, PlayerMedal


class CareerAchievementsSyncService:
    STAT_LABELS = {
        MedalType.Unit.MATCHES: 'matches',
        MedalType.Unit.CLEAN_SHEETS: 'clean sheets',
        MedalType.Unit.GOALS: 'goals',
        MedalType.Unit.ASSISTS: 'assists',
    }

    def __init__(self, stdout: Callable[[str], None] | None = None):
        self.stdout = stdout

    def sync(self, dry_run: bool = False):
        medals_by_stat = self._load_career_medals()

        added_total = 0
        removed_total = 0
        updated_dates_total = 0
        processed_players = 0

        for stat_key, medals in medals_by_stat.items():
            thresholds = ', '.join(str(item['threshold']) for item in medals)
            self._write(f'{stat_key}: {thresholds}')

        for player in self._get_players():
            processed_players += 1
            added, removed, updated_dates = self._sync_player(player, medals_by_stat, dry_run=dry_run)
            added_total += added
            removed_total += removed
            updated_dates_total += updated_dates

        summary = {
            'processed_players': processed_players,
            'added': added_total,
            'removed': removed_total,
            'updated_dates': updated_dates_total,
        }
        mode_label = 'Dry run' if dry_run else 'Sync complete'
        self._write(
            f'{mode_label}: processed {processed_players} players, '
            f'added {added_total} medal grants, removed {removed_total} medal grants, '
            f'updated {updated_dates_total} award dates'
        )
        return summary

    def _write(self, message: str):
        if self.stdout is not None:
            self.stdout(message)

    def _load_career_medals(self):
        medal_types = list(
            MedalType.objects.filter(kind=MedalType.Kind.CAREER_MILESTONE).order_by('unit', 'threshold', 'id')
        )
        medals_by_type = defaultdict(list)
        for medal in Medal.objects.filter(
            medal_type__kind=MedalType.Kind.CAREER_MILESTONE,
        ).select_related('medal_type'):
            medals_by_type[medal.medal_type_id].append(medal)
        medals_by_stat = defaultdict(list)

        for medal_type in medal_types:
            if medal_type.unit not in self.STAT_LABELS:
                raise CommandError(f'Unsupported career medal unit: {medal_type.unit or "<empty>"}')
            if not medal_type.threshold:
                raise CommandError(f'Career medal type has no threshold: {medal_type.code}')

            medals = medals_by_type.get(medal_type.id, [])
            if len(medals) != 1:
                raise CommandError(
                    f'Expected exactly one medal for career medal type {medal_type}, found {len(medals)}'
                )
            medal = medals[0]

            medals_by_stat[medal_type.unit].append({'medal': medal, 'threshold': medal_type.threshold})

        missing_stats = sorted(set(self.STAT_LABELS) - set(medals_by_stat))
        if missing_stats:
            raise CommandError(f'Missing career medal types for stats: {", ".join(missing_stats)}')

        return dict(medals_by_stat)

    def _get_players(self):
        return (
            Player.objects.filter(
                Q(played_matches__match__is_played=True)
                | Q(medals__medal__medal_type__kind=MedalType.Kind.CAREER_MILESTONE)
            )
            .distinct()
            .only('id', 'nickname')
            .order_by('id')
            .iterator(chunk_size=200)
        )

    def _sync_player(self, player, medals_by_stat, dry_run=False):
        current_grants = {
            grant.medal_id: grant
            for grant in PlayerMedal.objects.filter(
                player=player,
                medal__medal_type__kind=MedalType.Kind.CAREER_MILESTONE,
            ).only('id', 'medal_id', 'awarded_at')
        }
        added = 0
        removed = 0
        updated_dates = 0

        for stat_key, medals in medals_by_stat.items():
            events = self._get_stat_events(player, stat_key)
            stat_value = events.count()
            target = self._pick_target_medal(medals, stat_value)
            family_ids = {item['medal'].id for item in medals}
            family_titles = {item['medal'].id: str(item['medal']) for item in medals}
            target_id = target['medal'].id if target else None

            to_add = {target_id} - current_grants.keys() if target_id else set()
            to_remove = (current_grants.keys() & family_ids) - ({target_id} if target_id else set())
            awarded_at = self._threshold_awarded_at(events, target['threshold']) if target else None
            target_grant = current_grants.get(target_id)
            update_date = target_grant is not None and target_grant.awarded_at != awarded_at

            if not to_add and not to_remove and not update_date:
                continue

            if not dry_run:
                if to_add:
                    target_grant = PlayerMedal.objects.create(
                        medal=target['medal'],
                        player=player,
                        awarded_at=awarded_at,
                    )
                    current_grants[target_id] = target_grant
                elif update_date:
                    target_grant.awarded_at = awarded_at
                    target_grant.save(update_fields=['awarded_at'])

                if to_remove:
                    PlayerMedal.objects.filter(player=player, medal_id__in=to_remove).delete()

            added += len(to_add)
            removed += len(to_remove)
            updated_dates += int(update_date)

            self._write(
                f'{player.nickname}: {self.STAT_LABELS[stat_key]}={stat_value} '
                f'add={self._format_medal_titles(to_add, family_titles)} '
                f'remove={self._format_medal_titles(to_remove, family_titles)} '
                f'awarded_at={awarded_at}'
            )

            for medal_id in to_remove:
                current_grants.pop(medal_id, None)

        return added, removed, updated_dates

    @staticmethod
    def _get_stat_events(player, stat_key):
        if stat_key == MedalType.Unit.MATCHES:
            events = player.played_matches.filter(match__is_played=True)
        elif stat_key == MedalType.Unit.GOALS:
            events = player.goals.filter(match__is_played=True)
        elif stat_key == MedalType.Unit.ASSISTS:
            events = player.assists.filter(match__is_played=True)
        elif stat_key == MedalType.Unit.CLEAN_SHEETS:
            events = player.clean_sheets.filter(match__is_played=True)
        else:
            raise CommandError(f'Unsupported career medal unit: {stat_key}')

        return events.annotate(
            event_date=Coalesce('match__match_date', 'match__numb_tour__date_to', 'match__numb_tour__date_from')
        ).order_by('event_date', 'match_id', 'id')

    @staticmethod
    def _threshold_awarded_at(events, threshold):
        awarded_at = events.values_list('event_date', flat=True)[threshold - 1]
        if awarded_at is None:
            raise CommandError(f'Could not determine award date for threshold {threshold}')
        return awarded_at

    @staticmethod
    def _pick_target_medal(medals, value):
        eligible = [item for item in medals if value >= item['threshold']]
        return eligible[-1] if eligible else None

    @staticmethod
    def _format_medal_titles(medal_ids, titles_by_id):
        return [titles_by_id[medal_id] for medal_id in sorted(medal_ids)]


def sync_career_achievements(*, dry_run: bool = False, stdout: Callable[[str], None] | None = None):
    service = CareerAchievementsSyncService(stdout=stdout)
    return service.sync(dry_run=dry_run)
