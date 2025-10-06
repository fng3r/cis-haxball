from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from balance.models import Balance
from balance.services import BalanceService


class Command(BaseCommand):
    help = 'Перевести монеты между пользователями'

    def add_arguments(self, parser):
        parser.add_argument('sender_username', type=str, help='Имя отправителя')
        parser.add_argument('recipient_username', type=str, help='Имя получателя')
        parser.add_argument('amount', type=Decimal, help='Количество монет для перевода')
        parser.add_argument('description', type=str, help='Описание операции')

    def handle(self, *args, **options):
        sender_username = options['sender_username']
        recipient_username = options['recipient_username']
        amount = options['amount']
        description = options['description']

        try:
            sender = User.objects.get(username=sender_username)
        except User.DoesNotExist:
            raise CommandError(f'Отправитель "{sender_username}" не найден')

        try:
            recipient = User.objects.get(username=recipient_username)
        except User.DoesNotExist:
            raise CommandError(f'Получатель "{recipient_username}" не найден')

        if amount <= 0:
            raise CommandError('Сумма должна быть положительной')

        if sender == recipient:
            raise CommandError('Нельзя переводить монеты самому себе')

        try:
            outgoing_transaction, incoming_transaction = BalanceService.transfer_coins(
                sender, recipient, amount, description
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Успешно переведено {amount} монет от {sender_username} к {recipient_username}. '
                    f'Баланс отправителя: {Balance.objects.get_user_balance(sender)}'
                )
            )
            self.stdout.write(self.style.SUCCESS(f'Баланс получателя: {Balance.objects.get_user_balance(recipient)}'))
        except Exception as e:
            raise CommandError(f'Ошибка при переводе монет: {str(e)}')
