from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tournament.services.medals_import import LegacyMedalImporter


class Command(BaseCommand):
    help = 'Classify legacy medals and optionally import them into the structured medal models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write structured medals. Without this flag the command only reports classification results.',
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Return an error when any legacy rows remain unresolved.',
        )
        parser.add_argument('--show-unresolved', type=int, default=30, help='Maximum unresolved rows to print.')

    def handle(self, *args, **options):
        apply = options['apply']
        with transaction.atomic():
            report = LegacyMedalImporter(apply=apply).run()
            problem_count = len(report.unresolved) + len(report.import_errors)
            if options['strict'] and problem_count:
                raise CommandError(f'{problem_count} legacy medal rows remain unresolved or failed to import')

        mode = 'APPLY' if apply else 'REPORT ONLY'
        self.stdout.write(f'Mode: {mode}')
        self.stdout.write(f'Processed: {report.processed}')
        self.stdout.write(f'Classified: {report.classified}')
        self.stdout.write(f'Skipped empty legacy definitions: {report.skipped_unassigned}')
        self.stdout.write(f'Unresolved: {len(report.unresolved)}')
        if apply:
            self.stdout.write(f'Imported: {report.imported}')
            self.stdout.write(f'Already mapped: {report.already_mapped}')
            self.stdout.write(f'Import errors: {len(report.import_errors)}')
            self.stdout.write(f'Resolution warnings: {len(report.resolution_warnings)}')

        if report.unresolved:
            self.stdout.write('Unresolved examples:')
            for row in report.unresolved[: options['show_unresolved']]:
                self.stdout.write(f'  - {row}')

        if report.import_errors:
            self.stdout.write('Import error examples:')
            for row in report.import_errors[: options['show_unresolved']]:
                self.stdout.write(f'  - {row}')
        if report.resolution_warnings:
            self.stdout.write('Resolution warning examples:')
            for row in report.resolution_warnings[: options['show_unresolved']]:
                self.stdout.write(f'  - {row}')
