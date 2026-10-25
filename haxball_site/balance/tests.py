from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from balance.models import Gift, ShopCategory, ShopItem, Transaction, UserGift
from balance.services import ShopService
from balance.views import _build_shop_groups


class ShopGiftAcquiredCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user(username='viewer')
        cls.other = User.objects.create_user(username='other')
        cls.gift = Gift.objects.create(slug='rose', name='Rose')
        cls.item = ShopItem.objects.create(
            slug='rose', name='Rose', product_type=ShopItem.ProductType.GIFT, gift=cls.gift, price=10
        )
        cls.empty_item = ShopItem.objects.create(
            slug='star',
            name='Star',
            product_type=ShopItem.ProductType.GIFT,
            gift=Gift.objects.create(slug='star', name='Star'),
            price=10,
        )

    def get_counts(self):
        groups = _build_shop_groups(self.viewer, Decimal('100'))
        return {entry['item'].pk: entry['item'].acquired_count for group in groups for entry in group['items']}

    def test_counts_all_gift_instances_without_multiplying_allowed_users(self):
        self.item.allowed_users.add(self.viewer, self.other)
        transaction = Transaction.objects.create(
            user=self.other,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            amount=30,
            balance_before=30,
            balance_after=0,
        )
        for owner in [self.viewer, self.other, self.other]:
            UserGift.objects.create(gift=self.gift, owner=owner, buyer=self.other, amount=10, transaction=transaction)

        with self.assertNumQueries(2):
            counts = self.get_counts()

        self.assertEqual(counts[self.item.pk], 3)
        self.assertEqual(counts[self.empty_item.pk], 0)

    def test_count_refreshes_after_purchase(self):
        balance = self.viewer.balance
        balance.current_balance = 100
        balance.save()
        self.assertEqual(self.get_counts()[self.item.pk], 0)

        ShopService.purchase_item(self.viewer, self.item)

        self.assertEqual(self.get_counts()[self.item.pk], 1)

    def test_groups_respect_category_and_item_positions_with_counts(self):
        later_category = ShopCategory.objects.create(title='First alphabetically', slug='later', position=20)
        earlier_category = ShopCategory.objects.create(title='Last alphabetically', slug='earlier', position=10)
        ShopItem.objects.filter(pk=self.item.pk).update(category=later_category, position=20)
        ShopItem.objects.filter(pk=self.empty_item.pk).update(category=later_category, position=10)
        tied_item = ShopItem.objects.create(
            slug='apple',
            name='Apple',
            product_type=ShopItem.ProductType.STUB,
            category=later_category,
            position=10,
            price=0,
        )

        groups = _build_shop_groups(self.viewer, Decimal('100'))

        self.assertEqual([group['category'] for group in groups], [earlier_category, later_category])
        self.assertEqual(
            [entry['item'].pk for entry in groups[1]['items']],
            [tied_item.pk, self.empty_item.pk, self.item.pk],
        )
