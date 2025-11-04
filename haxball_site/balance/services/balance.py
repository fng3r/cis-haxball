from decimal import Decimal
from typing import Tuple

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction

from balance.models import Balance, Transaction


class BalanceService:
    """Service layer for balance operations"""

    @staticmethod
    def add_coins(user: User, amount: Decimal, description: str, admin_user: User | None = None) -> Transaction:
        """Add coins to user balance"""
        if amount <= 0:
            raise ValidationError('Amount must be positive')

        with transaction.atomic():
            balance = Balance.objects.select_for_update().get(user=user)

            transaction_obj = Transaction(
                user=user,
                transaction_type=Transaction.TransactionType.DEPOSIT,
                amount=amount,
                description=description,
                admin_user=admin_user,
                balance_before=balance.current_balance,
                balance_after=balance.current_balance + amount,
            )

            balance.current_balance += amount
            balance.save(update_fields=['current_balance', 'updated_at'])
            transaction_obj.save()

            return transaction_obj

    @staticmethod
    def subtract_coins(user: User, amount: Decimal, description: str, admin_user: User | None = None) -> Transaction:
        """Subtract coins from user balance"""
        if amount <= 0:
            raise ValidationError('Amount must be positive')

        with transaction.atomic():
            balance = Balance.objects.select_for_update().get(user=user)

            if balance.current_balance < amount:
                raise ValidationError(f'Insufficient funds. Available: {balance.current_balance}, Required: {amount}')

            transaction_obj = Transaction(
                user=user,
                transaction_type=Transaction.TransactionType.WITHDRAWAL,
                amount=amount,
                description=description,
                admin_user=admin_user,
                balance_before=balance.current_balance,
                balance_after=balance.current_balance - amount,
            )

            balance.current_balance -= amount
            balance.save(update_fields=['current_balance', 'updated_at'])
            transaction_obj.save()

            return transaction_obj

    @staticmethod
    def transfer_coins(
        sender: User, recipient: User, amount: Decimal, description: str, admin_user: User | None = None
    ) -> Tuple[Transaction, Transaction]:
        """Transfer coins between users"""
        if amount <= 0:
            raise ValidationError('Amount must be positive')

        if sender == recipient:
            raise ValidationError('Cannot transfer coins to yourself')

        # Sort users to prevent deadlocks
        users = sorted([sender, recipient], key=lambda u: u.id)

        with transaction.atomic():
            balances = []
            for user in users:
                balance = Balance.objects.select_for_update().get(user=user)
                balances.append(balance)

            sender_balance = balances[0] if balances[0].user == sender else balances[1]
            recipient_balance = balances[1] if balances[0].user == sender else balances[0]

            if sender_balance.current_balance < amount:
                raise ValidationError(
                    f'Insufficient funds. Available: {sender_balance.current_balance}, Required: {amount}'
                )

            outgoing_transaction = Transaction(
                user=sender,
                transaction_type=Transaction.TransactionType.TRANSFER_OUT,
                amount=amount,
                description=f'{description} (transfer to {recipient.username})',
                admin_user=admin_user,
                balance_before=sender_balance.current_balance,
                balance_after=sender_balance.current_balance - amount,
                related_user=recipient,
            )

            incoming_transaction = Transaction(
                user=recipient,
                transaction_type=Transaction.TransactionType.TRANSFER_IN,
                amount=amount,
                description=f'{description} (transfer from {sender.username})',
                admin_user=admin_user,
                balance_before=recipient_balance.current_balance,
                balance_after=recipient_balance.current_balance + amount,
                related_user=sender,
            )

            sender_balance.current_balance -= amount
            recipient_balance.current_balance += amount

            sender_balance.save(update_fields=['current_balance', 'updated_at'])
            recipient_balance.save(update_fields=['current_balance', 'updated_at'])
            outgoing_transaction.save()
            incoming_transaction.save()

            return outgoing_transaction, incoming_transaction
