import csv
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from balance.models import Balance
from balance.services import BalanceService


class Command(BaseCommand):
    help = 'Добавить монеты пользователям из CSV файла'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Путь к CSV файлу с данными')
        parser.add_argument('--dry-run', action='store_true', help='Показать что будет сделано без выполнения операций')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        dry_run = options['dry_run']

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                success_count = 0
                error_count = 0
                errors = []

                for row_num, row in enumerate(reader, start=2):
                    try:
                        username = row['username'].strip()
                        amount_str = row['amount'].strip()
                        description = row['description'].strip()

                        if not username or not amount_str or not description:
                            raise ValueError('Все поля должны быть заполнены')

                        try:
                            amount = Decimal(amount_str)
                        except (ValueError, TypeError):
                            raise ValueError(f'Неверный формат суммы: {amount_str}')

                        if amount <= 0:
                            raise ValueError('Сумма должна быть положительной')

                        try:
                            user = User.objects.get(username=username)
                        except User.DoesNotExist:
                            raise ValueError(f'Пользователь "{username}" не найден')

                        if dry_run:
                            self.stdout.write(
                                f'[DRY RUN] Строка {row_num}: '
                                + f'Добавить {amount} монет пользователю {username} - "{description}"'
                            )
                        else:
                            _ = BalanceService.add_coins(user, amount, description)

                            self.stdout.write(
                                f'✓ Строка {row_num}: Добавлено {amount} монет пользователю {username}. '
                                f'Новый баланс: {Balance.objects.get_user_balance(user)}'
                            )

                        success_count += 1

                    except Exception as e:
                        error_count += 1
                        error_msg = f'Строка {row_num}: {str(e)}'
                        errors.append(error_msg)
                        self.stdout.write(self.style.ERROR(f'✗ {error_msg}'))

                self.stdout.write('\n' + '=' * 50)
                if dry_run:
                    self.stdout.write(self.style.WARNING(f'[DRY RUN] Обработано записей: {success_count}'))
                    self.stdout.write(self.style.WARNING(f'[DRY RUN] Ошибок: {error_count}'))
                else:
                    self.stdout.write(self.style.SUCCESS(f'Успешно обработано: {success_count} записей'))
                    if error_count > 0:
                        self.stdout.write(self.style.ERROR(f'Ошибок: {error_count}'))
                        self.stdout.write('\nДетали ошибок:')
                        for error in errors:
                            self.stdout.write(f'  - {error}')

        except FileNotFoundError:
            raise CommandError(f'Файл "{csv_file}" не найден')
        except Exception as e:
            raise CommandError(f'Ошибка при обработке файла: {str(e)}')
