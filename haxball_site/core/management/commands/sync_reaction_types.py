import json
from typing import Any
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import ReactionType


class Command(BaseCommand):
    help = 'Sync reaction types from external emoji registry'

    def add_arguments(self, parser):
        parser.add_argument('--url', dest='registry_url', default=None)
        parser.add_argument('--limit', dest='limit', type=int, default=None)
        parser.add_argument('--deactivate-missing', action='store_true', default=False)

    def handle(self, *args, **options):
        registry_url = options['registry_url'] or getattr(
            settings,
            'REACTIONS_REGISTRY_URL',
            'https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json',
        )
        limit = options['limit']
        deactivate_missing = options['deactivate_missing']

        if limit is not None and limit <= 0:
            raise CommandError('--limit must be greater than 0')

        try:
            rows = self.fetch_registry_reactions(registry_url)
        except Exception as exc:
            raise CommandError(f'Unable to fetch reactions from {registry_url}: {exc}') from exc

        if not rows:
            raise CommandError('Registry returned no reactions')

        created_count = 0
        updated_count = 0
        selected_rows = rows if limit is None else rows[:limit]
        selected_codes = []

        for index, row in enumerate(selected_rows, start=1):
            selected_codes.append(row['code'])
            _, created = ReactionType.objects.update_or_create(
                code=row['code'],
                defaults={
                    'emoji': row['emoji'],
                    'label': row['label'],
                    'category': row.get('category') or 'Other',
                    'sort_order': index * 10,
                    'is_active': True,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        if deactivate_missing:
            ReactionType.objects.exclude(code__in=selected_codes).update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                f'Synced reaction types from {registry_url}. Created: {created_count}, updated: {updated_count}.'
            )
        )

    def fetch_registry_reactions(self, registry_url: str, timeout: int = 8) -> list[dict[str, Any]]:
        """
        Load emoji records from the gemoji JSON format.
        Example source: https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json
        """
        request = Request(registry_url, headers={'User-Agent': 'cis-haxball-reactions/1.0'})
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            payload = json.loads(response.read().decode('utf-8'))

        results: list[dict[str, Any]] = []
        for row in payload:
            emoji = row.get('emoji')
            aliases = row.get('aliases') or []
            if not emoji or not aliases:
                continue

            code = str(aliases[0]).strip().lower().replace('+', '_').replace('-', '_')
            if not code:
                continue

            description = (row.get('description') or code).strip()
            label = description[:64]
            category = (row.get('category') or row.get('group') or 'Other').strip()[:64]
            results.append({'code': code, 'emoji': emoji, 'label': label, 'category': category or 'Other'})

        return results
