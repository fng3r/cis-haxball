import csv

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import UserNicknameHistoryItem

from ...models import Player, PlayerRating, PlayerRatingVersion

DEFAULT_STATUS = PlayerRating.RatingUpdateStatus.EXPERT_REVIEW
VALID_STATUSES = {s.value: s for s in PlayerRating.RatingUpdateStatus}


def parse_status(raw: str) -> str:
    """Parse rating_update_status from CSV; default to expert_review if missing or invalid."""
    if not raw or not raw.strip():
        return DEFAULT_STATUS
    key = raw.strip().lower()
    return VALID_STATUSES.get(key, DEFAULT_STATUS)


class Command(BaseCommand):
    help = (
        'Import players rating from csv file. '
        'CSV: nickname, raw_points, points, grade [, rating_update_status]. '
        'Optional last column: expert_review, inactivity_decrease, frozen (default: expert_review).'
    )

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='path to .csv file')
        parser.add_argument('-V', dest='version', type=int, help='rating version')
        parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options) -> str | None:
        filename = options['filename']
        version = options['version']
        dry_run = options.get('dry_run', False)

        if not version:
            last_version = PlayerRatingVersion.objects.order_by('-number').first()
            version = last_version.number + 1 if last_version else 1

        rating_version, created = PlayerRatingVersion.objects.get_or_create(
            number=version,
            defaults={'date': timezone.localdate()},
        )

        if not created:
            self.stderr.write(f'ERROR: Version {version} already exists')
            return

        rows_count = 0
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.reader(file.readlines())
            for row in reader:
                if len(row) < 4:
                    self.stderr.write(f'ERROR: Row has {len(row)} columns, need at least 4: {row}')
                    raise SystemExit(1)
                nickname, raw_points, points, grade = row[0], row[1], row[2], row[3]
                status_raw = row[4] if len(row) > 4 else ''
                status = parse_status(status_raw)

                if raw_points == '':
                    raw_rating = None
                else:
                    try:
                        raw_rating = float(raw_points.replace(',', '.'))
                    except ValueError:
                        self.stderr.write(f'ERROR: Invalid rating points {raw_points} for player {nickname}')
                        raise
                rating = int(points)
                player = Player.objects.filter(nickname=nickname).first()
                if not player:
                    user = UserNicknameHistoryItem.objects.filter(nickname=nickname).first()
                    if user:
                        player = user.user.user_player

                if not player:
                    self.stdout.write(f'WARN: Player {nickname} not found', self.style.WARNING)
                else:
                    if not dry_run:
                        PlayerRating.objects.create(
                            version=rating_version,
                            player=player,
                            raw_rating_points=raw_rating,
                            rating_points=rating,
                            grade=grade,
                            rating_update_status=status,
                        )
                    rows_count += 1

        self.stdout.write(f'{rows_count} entries was imported from file {filename}', self.style.SUCCESS)
