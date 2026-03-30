from django.core.management.base import BaseCommand

from tournament.services.achievements import sync_career_achievements


class Command(BaseCommand):
    help = 'Sync career achievements for matches, goals, assists, and clean sheets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without modifying achievements',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        summary = sync_career_achievements(dry_run=dry_run, stdout=self.stdout.write)
        mode_style = self.style.WARNING if dry_run else self.style.SUCCESS
        self.stdout.write(
            mode_style(
                f'Finished sync_stats_achievements: processed {summary["processed_players"]} players, '
                f'added {summary["added"]}, removed {summary["removed"]}'
            )
        )
