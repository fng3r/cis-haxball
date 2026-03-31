import re
from collections import defaultdict
from typing import Callable

from django.core.management.base import CommandError

from tournament.models import Achievements, Player


class CareerAchievementsSyncService:
    CAREER_TITLE_SEARCH = 'за карьеру'
    THRESHOLD_PATTERN = re.compile(r'(\d+)')
    CLEAN_SHEET_EVENT = 'CLN'
    STAT_PATTERNS = {
        'matches': ('сыгранных матч',),
        'clean_sheets': ('сухих тайм',),
        'goals': ('забитых голов',),
        'assists': ('голевых передач',),
    }
    STAT_LABELS = {
        'matches': 'matches',
        'clean_sheets': 'clean sheets',
        'goals': 'goals',
        'assists': 'assists',
    }

    def __init__(self, stdout: Callable[[str], None] | None = None):
        self.stdout = stdout

    def sync(self, dry_run: bool = False):
        achievements_by_stat = self._load_career_achievements()

        added_total = 0
        removed_total = 0
        processed_players = 0

        for stat_key, achievements in achievements_by_stat.items():
            thresholds = ', '.join(str(item['threshold']) for item in achievements)
            self._write(f'{stat_key}: {thresholds}')

        for player in self._get_players():
            processed_players += 1
            added, removed = self._sync_player(player, achievements_by_stat, dry_run=dry_run)
            added_total += added
            removed_total += removed

        summary = {
            'processed_players': processed_players,
            'added': added_total,
            'removed': removed_total,
        }
        mode_label = 'Dry run' if dry_run else 'Sync complete'
        self._write(
            f'{mode_label}: processed {processed_players} players, '
            f'added {added_total} achievement links, removed {removed_total} achievement links'
        )
        return summary

    def _write(self, message: str):
        if self.stdout is not None:
            self.stdout(message)

    def _load_career_achievements(self):
        achievements = (
            Achievements.objects.filter(title__icontains=self.CAREER_TITLE_SEARCH)
            .order_by('position_number', 'id')
            .only('id', 'title', 'position_number')
        )

        achievements_by_stat = defaultdict(list)

        for achievement in achievements:
            stat_key = self._detect_stat_key(achievement.title)
            threshold = self._extract_threshold(achievement.title)
            achievements_by_stat[stat_key].append({'achievement': achievement, 'threshold': threshold})

        missing_stats = sorted(set(self.STAT_PATTERNS) - set(achievements_by_stat))
        if missing_stats:
            raise CommandError(
                f'Missing career achievements for stats: {", ".join(missing_stats)}. '
                f'Search query: "{self.CAREER_TITLE_SEARCH}"'
            )

        for stat_key, items in achievements_by_stat.items():
            items.sort(key=lambda item: item['threshold'])

        return dict(achievements_by_stat)

    def _get_players(self):
        return (
            Player.objects.filter(played_matches__match__is_played=True)
            .distinct()
            .only('id', 'nickname')
            .order_by('id')
            .iterator(chunk_size=200)
        )

    def _sync_player(self, player, achievements_by_stat, dry_run=False):
        current_ids = set(
            player.achievements.filter(title__icontains=self.CAREER_TITLE_SEARCH).values_list('id', flat=True)
        )
        added = 0
        removed = 0

        stat_values = {
            'matches': player.played_matches.filter(match__is_played=True).count(),
            'goals': player.goals.filter(match__is_played=True).count(),
            'assists': player.assists.filter(match__is_played=True).count(),
            'clean_sheets': player.event.filter(match__is_played=True, event=self.CLEAN_SHEET_EVENT).count(),
        }

        for stat_key, achievements in achievements_by_stat.items():
            target_achievement = self._pick_target_achievement(achievements, stat_values[stat_key])
            family_ids = {item['achievement'].id for item in achievements}
            family_titles = {item['achievement'].id: item['achievement'].title for item in achievements}
            target_id = target_achievement.id if target_achievement else None

            to_add = {target_id} - current_ids if target_id else set()
            to_remove = (current_ids & family_ids) - ({target_id} if target_id else set())

            if not to_add and not to_remove:
                continue

            if not dry_run:
                if to_add:
                    player.achievements.add(*to_add)
                if to_remove:
                    player.achievements.remove(*to_remove)

            added += len(to_add)
            removed += len(to_remove)

            self._write(
                f'{player.nickname}: {self.STAT_LABELS[stat_key]}={stat_values[stat_key]} '
                f'add={self._format_achievement_titles(to_add, family_titles)} '
                f'remove={self._format_achievement_titles(to_remove, family_titles)}'
            )

            current_ids |= to_add
            current_ids -= to_remove

        return added, removed

    def _pick_target_achievement(self, achievements, value):
        eligible = [item['achievement'] for item in achievements if value >= item['threshold']]
        return eligible[-1] if eligible else None

    def _detect_stat_key(self, title):
        lowered_title = title.lower()
        for stat_key, patterns in self.STAT_PATTERNS.items():
            if any(pattern in lowered_title for pattern in patterns):
                return stat_key
        raise CommandError(f'Could not detect career achievement stat type from title: {title}')

    def _extract_threshold(self, title):
        match = self.THRESHOLD_PATTERN.search(title)
        if not match:
            raise CommandError(f'Could not extract threshold from title: {title}')
        return int(match.group(1))

    def _format_achievement_titles(self, achievement_ids, titles_by_id):
        return [titles_by_id[achievement_id] for achievement_id in sorted(achievement_ids)]


def sync_career_achievements(*, dry_run: bool = False, stdout: Callable[[str], None] | None = None):
    service = CareerAchievementsSyncService(stdout=stdout)
    return service.sync(dry_run=dry_run)
