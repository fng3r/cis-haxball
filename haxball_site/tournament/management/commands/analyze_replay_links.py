import re
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlparse

from django.core.management.base import BaseCommand

from tournament.models import Match

FILTERED_HOST_TOKENS = ('cis-haxball',)


HEX_32_RE = re.compile(r'^[0-9a-f]{32}$', re.IGNORECASE)
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)
INT_RE = re.compile(r'^\d+$')


def _normalize_segment(segment: str) -> str:
    if HEX_32_RE.match(segment):
        return '{hex32}'
    if UUID_RE.match(segment):
        return '{uuid}'
    if INT_RE.match(segment):
        return '{int}'
    if segment.lower().endswith('.hbr2'):
        return '{hbr2_file}'
    return segment.lower()


def infer_replay_link_type(url: str) -> str:
    value = (url or '').strip()
    if not value:
        return 'empty'

    parsed = urlparse(value)
    scheme = (parsed.scheme or '').lower()
    host = (parsed.netloc or '').lower()
    path = parsed.path or ''

    if not scheme and not host and value.startswith('/'):
        return f'path-only:{path}'
    if not host:
        return f'non-url:{value}'

    segments = [seg for seg in path.split('/') if seg]
    normalized_segments = [_normalize_segment(seg) for seg in segments]
    normalized_path = '/' + '/'.join(normalized_segments) if normalized_segments else '/'

    query_keys = sorted({k.lower() for k, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    query_signature = '&'.join(query_keys) if query_keys else '-'

    return f'{scheme}://{host}{normalized_path}?{query_signature}'


class Command(BaseCommand):
    help = 'Analyze replay link types from Match.replays and print breakdown with example match IDs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sample-size',
            type=int,
            default=5,
            help='How many example match IDs to show per type',
        )
        parser.add_argument(
            '--show-sample-urls',
            action='store_true',
            help='Also print sample replay URLs for each inferred type',
        )

    def handle(self, *args, **options):
        sample_size = max(1, options['sample_size'])
        show_sample_urls = options['show_sample_urls']

        type_counts = Counter()
        host_counts = Counter()
        examples = defaultdict(list)
        sample_urls = defaultdict(list)

        total_matches_with_replays = 0
        total_replay_links = 0
        filtered_out_links = 0

        queryset = Match.objects.exclude(replays=[]).values_list('id', 'replays')
        for match_id, replays in queryset.iterator():
            total_matches_with_replays += 1
            for raw_link in replays or []:
                total_replay_links += 1
                value = (raw_link or '').strip()
                parsed = urlparse(value)
                host = (parsed.netloc or '').lower() or '<no-host>'
                if any(token in host for token in FILTERED_HOST_TOKENS):
                    filtered_out_links += 1
                    continue
                link_type = infer_replay_link_type(value)

                type_counts[link_type] += 1
                host_counts[host] += 1

                if len(examples[link_type]) < sample_size:
                    examples[link_type].append(match_id)
                if len(sample_urls[link_type]) < sample_size:
                    sample_urls[link_type].append(value)

        self.stdout.write(f'Total matches with replays: {total_matches_with_replays}')
        self.stdout.write(f'Total replay links: {total_replay_links}')
        self.stdout.write(f'Filtered out CIS Haxball links: {filtered_out_links}')

        self.stdout.write('\nType breakdown:')
        for link_type, count in type_counts.most_common():
            self.stdout.write(f'- {link_type}: {count} | example match IDs: {examples[link_type]}')
            if show_sample_urls:
                for sample_url in sample_urls[link_type]:
                    self.stdout.write(f'    url: {sample_url}')

        self.stdout.write('\nHost breakdown (top 20):')
        for host, count in host_counts.most_common(20):
            self.stdout.write(f'- {host}: {count}')
