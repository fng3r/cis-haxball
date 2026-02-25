import re

from django.core.management.base import BaseCommand

from balance.models import ShopItem

from core.models import NewComment, Post

PATTERNS = {
    'iframe': re.compile(r'<iframe\b', re.IGNORECASE),
    'video': re.compile(r'<video\b', re.IGNORECASE),
    'source': re.compile(r'<source\b', re.IGNORECASE),
    'img': re.compile(r'<img\b', re.IGNORECASE),
    'spoiler_div': re.compile(r'<div[^>]*class="[^"]*spoiler', re.IGNORECASE),
    'mention_data_attr': re.compile(r'data-mentioned-user-id=', re.IGNORECASE),
    'inline_style_attr': re.compile(r'\sstyle=', re.IGNORECASE),
    'style_tag': re.compile(r'<style\b', re.IGNORECASE),
    'table_tag': re.compile(r'<table\b', re.IGNORECASE),
    'font_tag': re.compile(r'<font\b', re.IGNORECASE),
    'emoji_span': re.compile(r'<span[^>]*class="[^"]*emoji', re.IGNORECASE),
    'unicode_emoji': re.compile(r'[\U0001F300-\U0001FAFF]'),
}


class Command(BaseCommand):
    help = 'Audit rich-text HTML markers in posts/comments/shop descriptions for CKEditor migration validation.'

    def add_arguments(self, parser):
        parser.add_argument('--samples', type=int, default=3, help='How many sample rows to print per marker/model')

    def handle(self, *args, **options):
        sample_limit = max(options['samples'], 0)
        datasets = [
            ('Post.body', Post.objects.exclude(body='').values_list('id', 'body')),
            ('NewComment.body', NewComment.objects.exclude(body='').values_list('id', 'body')),
            ('ShopItem.description', ShopItem.objects.exclude(description='').values_list('id', 'description')),
        ]

        for dataset_name, queryset in datasets:
            rows = list(queryset)
            total = len(rows)
            self.stdout.write(self.style.NOTICE(f'[{dataset_name}] total_nonempty={total}'))
            if not total:
                self.stdout.write('')
                continue

            for marker_name, pattern in PATTERNS.items():
                matched = [(row_id, value) for row_id, value in rows if pattern.search(value or '')]
                if not matched:
                    continue

                percent = (len(matched) / total) * 100
                self.stdout.write(f'  {marker_name}: {len(matched)} ({percent:.2f}%)')
                for row_id, value in matched[:sample_limit]:
                    snippet = re.sub(r'\s+', ' ', value).strip()[:220]
                    self.stdout.write(f'    id={row_id}: {snippet}')

            average_length = sum(len(value) for _, value in rows) / total
            self.stdout.write(f'  avg_length={average_length:.1f}')
            self.stdout.write('')
