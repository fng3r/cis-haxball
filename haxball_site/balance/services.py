from datetime import timedelta
from decimal import Decimal
from typing import Tuple

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from balance.models import Balance, ShopItem, ShopPurchase, Transaction
from core.models import Subscription, UserIcon


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


class ShopService:
    """Service layer for shop operations"""

    @staticmethod
    def purchase_item(user: User, item: ShopItem) -> ShopPurchase:
        if not item.is_active:
            raise ValidationError('Этот товар недоступен для покупки')

        with transaction.atomic():
            transaction_obj = BalanceService.subtract_coins(
                user=user,
                amount=item.price,
                description=f'Покупка: {item.name}',
            )

            subscription = None
            metadata: dict[str, object] = {}

            if item.product_type == ShopItem.ProductType.SUBSCRIPTION:
                subscription = ShopService._activate_subscription(user, item)
                metadata = {
                    'subscription_id': subscription.id,
                    'starts_at': subscription.starts_at.isoformat(),
                    'expires_at': subscription.expires_at.isoformat(),
                    'tier': subscription.tier,
                }

            purchase = ShopPurchase.objects.create(
                user=user,
                item=item,
                amount=item.price,
                transaction=transaction_obj,
                metadata=metadata,
            )

            return purchase

    @staticmethod
    def _activate_subscription(user: User, item: ShopItem) -> Subscription:
        tier = item.subscription_tier or Subscription.TIER_1
        duration_in_days = item.subscription_duration_in_days or 30

        now = timezone.now()
        latest_subscription = Subscription.objects.by_user(user).filter(disabled=False).order_by('-expires_at').first()

        if latest_subscription and latest_subscription.expires_at > now:
            starts_at = latest_subscription.expires_at
        else:
            starts_at = now

        expires_at = starts_at + timedelta(days=duration_in_days)

        subscription = Subscription.objects.create(
            user=user,
            tier=tier,
            starts_at=starts_at,
            expires_at=expires_at,
            disabled=False,
        )

        ShopService._grant_premium_icon(user)

        return subscription

    @staticmethod
    def _grant_premium_icon(user: User) -> None:
        profile = user.user_profile
        icon = UserIcon.objects.filter(title='Premium Star').first()
        if not icon:
            return

        icon.user.add(profile)
