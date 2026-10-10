from django.contrib.auth.models import User

from balance.models import Gift, Transaction, UserGift


class GiftService:
    """Helper for granting gift ownership. Charging is handled by ShopService."""

    @staticmethod
    def grant_gift(
        *,
        buyer: User,
        owner: User,
        gift: Gift,
        transaction_obj: Transaction,
        amount,
        message: str = '',
    ) -> UserGift:
        return UserGift.objects.create(
            gift=gift,
            owner=owner,
            buyer=buyer,
            amount=amount,
            transaction=transaction_obj,
            message=(message or '').strip()[:50],
        )
