"""Repository migrations are generated locally. Add the required experimental-data transfer before applying them."""

from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = 'Generate replay schema migration and preserve existing experimental LocalReplayAnalysis data'

    def handle(self, **options):
        call_command('makemigrations', 'tournament', interactive=False)
        loader = MigrationLoader(connection)
        for key, migration in loader.disk_migrations.items():
            if key[0] != 'tournament' or key in loader.applied_migrations:
                continue
            import importlib

            module = importlib.import_module(migration.__module__)
            path = Path(module.__file__)
            source = path.read_text()
            if 'copy_previous_analyses' in source:
                continue
            removes = [
                op
                for op in migration.operations
                if op.__class__.__name__ == 'DeleteModel' and op.name.lower() == 'localreplayanalysis'
            ]
            if not removes:
                continue
            marker = (
                "        migrations.RemoveField(\n            model_name='localreplayanalysis',\n"
                "            name='match',\n        ),"
            )
            if marker not in source:
                raise CommandError(
                    'Review LocalReplayAnalysis deletion: insert copy_previous_analyses before removing its fields.'
                )
            source = source.replace(
                'from django.db import migrations, models',
                'from django.db import migrations, models\n'
                'from tournament.replay_schema_upgrade import copy_previous_analyses, restore_previous_analyses',
            )
            source = source.replace(
                marker, '        migrations.RunPython(copy_previous_analyses, restore_previous_analyses),\n' + marker
            )
            path.write_text(source)
            self.stdout.write(f'Added existing-data transfer to {path.name}')
