import csv

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ...models import Player, PlayerTransfer, Season, Team


class Command(BaseCommand):
    help = 'Generate transfers from CSV file with team, username, and captain/captain assistant roles'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='Path to the CSV file containing transfer data')
        parser.add_argument(
            '--season', type=int, help='Season number for transfers (defaults to active season)', default=None
        )
        parser.add_argument(
            '--dry-run', action='store_true', help='Show what would be done without actually creating transfers'
        )

    def handle(self, *args, **options):
        filename_path = options['filename']
        season_number = options['season']
        dry_run = options['dry_run']

        # Get season
        try:
            if season_number:
                season = Season.objects.get(number=season_number)
            else:
                season = Season.objects.filter(is_active=True).first()
                if not season:
                    raise CommandError('No active season found. Please specify a season number.')
        except Season.DoesNotExist:
            raise CommandError(f'Season with number {season_number} does not exist.')

        self.stdout.write(f'Using season: {season.title} (number: {season.number})')

        # Parse CSV file
        try:
            with open(filename_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                transfers_data = list(csv_reader)
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {filename_path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

        if not transfers_data:
            raise CommandError('CSV file is empty or has no valid data rows.')

        # Validate CSV structure
        required_fields = ['team', 'username']
        for field in required_fields:
            if field not in transfers_data[0]:
                raise CommandError(f'CSV file must contain "{field}" column.')

        self.stdout.write(f'Found {len(transfers_data)} rows in CSV file.')

        # Process transfers
        successful_transfers = 0
        warnings = []
        errors = []

        for row_num, row in enumerate(transfers_data, 1):
            team_name = row['team'].strip()
            username = row['username'].strip()
            role = row.get('role', '').strip().lower() if 'role' in row else ''

            # Check if team exists
            try:
                team = Team.objects.get(title=team_name)
            except Team.DoesNotExist:
                warnings.append(f'Row {row_num}: Team "{team_name}" does not exist.')
                continue

            # Validate user exists
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                warnings.append(f'Row {row_num}: User "{username}" does not exist.')
                continue

            # Validate player exists
            try:
                player = Player.objects.get(name=user)
            except Player.DoesNotExist:
                warnings.append(f'Row {row_num}: Player for user "{username}" does not exist.')
                continue

            # Check if player is already in this team
            if player.team == team:
                warnings.append(f'Row {row_num}: Player "{username}" is already in team "{team_name}".')
                continue

            # Validate role if specified
            valid_roles = ['c', 'a']
            if role and role not in valid_roles:
                warnings.append(f'Row {row_num}: Invalid role "{role}". Valid roles: c (captain), a (assistant)')

            # Create transfer
            if not dry_run:
                try:
                    with transaction.atomic():
                        # Create the transfer
                        PlayerTransfer.objects.create(
                            trans_player=player,
                            from_team=player.team,
                            to_team=team,
                            season_join=season,
                            date_join=timezone.now().date(),
                            is_technical=False,
                        )

                        # Assign captain/captain assistant role if specified
                        if role == 'c':
                            if team.captain and team.captain != player:
                                warnings.append(f'Row {row_num}: Team "{team_name}" already has a captain. Replacing.')
                            team.captain = player
                            team.save(update_fields=['captain'])
                        elif role == 'a':
                            if team.captain_assistant and team.captain_assistant != player:
                                warnings.append(
                                    f'Row {row_num}: Team "{team_name}" already has a captain assistant. Replacing.'
                                )
                            team.captain_assistant = player
                            team.save(update_fields=['captain_assistant'])

                        successful_transfers += 1
                        self.stdout.write(
                            f'✓ Row {row_num}: {username} transferred to {team_name}' + (f' ({role})' if role else '')
                        )

                except Exception as e:
                    errors.append(f'Row {row_num}: Error creating transfer: {str(e)}')
            else:
                # Dry run - just show what would happen
                successful_transfers += 1
                self.stdout.write(
                    f'[DRY RUN] Row {row_num}: {username} would be transferred to {team_name}'
                    + (f' ({role})' if role else '')
                )

        # Summary
        self.stdout.write('\n' + '=' * 50)
        self.stdout.write('SUMMARY:')
        self.stdout.write('=' * 50)

        if successful_transfers > 0:
            action = 'would be created' if dry_run else 'created'
            self.stdout.write(self.style.SUCCESS(f'✓ {successful_transfers} transfers {action} successfully.'))

        if warnings:
            self.stdout.write(f'\n⚠️  {len(warnings)} warnings:')
            for warning in warnings:
                self.stdout.write(f'  - {warning}')

        if errors:
            self.stdout.write(f'\n❌ {len(errors)} errors:')
            for error in errors:
                self.stdout.write(f'  - {error}')

        if dry_run:
            self.stdout.write('\nThis was a dry run. No actual transfers were created.')
            self.stdout.write('Run without --dry-run to create the transfers.')
