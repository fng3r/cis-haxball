import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Subscription


class BalanceManager(models.Manager):
    def get_user_balance(self, user: User) -> Decimal:
        """Получить текущий баланс пользователя"""
        balance = self.get(user=user)
        return balance.current_balance


class Balance(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь', related_name='balance')
    current_balance = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name='Текущий баланс'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    objects = BalanceManager()

    class Meta:
        verbose_name = 'Баланс'
        verbose_name_plural = 'Балансы'
        ordering = ['-updated_at']

    def __str__(self):
        return f'Баланс {self.user.username}: {self.current_balance} CC'

    @staticmethod
    @receiver(post_save, sender=User)
    def create_user_balance(sender, instance, created, **kwargs):
        """Автоматически создавать баланс при создании пользователя"""
        if created:
            Balance.objects.create(user=instance)


class TransactionManager(models.Manager):
    """Manager для работы с транзакциями"""

    def get_user_transactions(self, user: User):
        """Получить все транзакции пользователя"""
        return self.filter(user=user).order_by('-created_at')

    def get_deposits(self, user: User | None = None):
        """Получить все пополнения"""
        return self._get_transactions([Transaction.TransactionType.DEPOSIT], user)

    def get_withdrawals(self, user: User | None = None):
        """Получить все списания"""
        return self._get_transactions([Transaction.TransactionType.WITHDRAWAL], user)

    def get_transfers(self, user: User | None = None):
        """Получить все переводы"""
        return self._get_transactions(
            [Transaction.TransactionType.TRANSFER_IN, Transaction.TransactionType.TRANSFER_OUT], user
        )

    def _get_transactions(self, transaction_types: list[str], user: User | None = None):
        """Получить все транзакции по типу"""
        queryset = self.filter(transaction_type__in=transaction_types)
        if user:
            queryset = queryset.filter(user=user)
        return queryset.order_by('-created_at')


class Transaction(models.Model):
    """
    Модель транзакции для отслеживания всех операций с балансом.
    Обеспечивает полную прозрачность и аудит всех операций.
    """

    class TransactionType(models.TextChoices):
        """Типы транзакций"""

        DEPOSIT = 'deposit', 'Пополнение'
        WITHDRAWAL = 'withdrawal', 'Списание'
        TRANSFER_IN = 'transfer_in', 'Перевод (входящий)'
        TRANSFER_OUT = 'transfer_out', 'Перевод (исходящий)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='ID транзакции')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь', related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices, verbose_name='Тип транзакции')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Сумма')
    description = models.CharField(max_length=500, verbose_name='Описание')

    admin_user = models.ForeignKey(
        User,
        limit_choices_to={'is_staff': True},
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Администратор',
        related_name='admin_transactions',
    )

    balance_before = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Баланс до операции')
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Баланс после операции')

    related_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Связанный пользователь',
        related_name='related_transactions',
        help_text='Для переводов - пользователь, с которым связана транзакция',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    objects = TransactionManager()

    class Meta:
        verbose_name = 'Транзакция'
        verbose_name_plural = 'Транзакции'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['transaction_type', 'created_at']),
        ]

    def __str__(self):
        return f'{self.get_transaction_type_display()} - {self.user.username}: {self.amount} CC'

    def clean(self):
        if self.amount <= 0:
            raise ValidationError('Сумма должна быть положительной')

        if (
            self.transaction_type in [self.TransactionType.TRANSFER_IN, self.TransactionType.TRANSFER_OUT]
            and not self.related_user
        ):
            raise ValidationError('Для переводов должен быть указан связанный пользователь')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_deposit(self) -> bool:
        return self.transaction_type == self.TransactionType.DEPOSIT

    @property
    def is_withdrawal(self) -> bool:
        return self.transaction_type == self.TransactionType.WITHDRAWAL

    @property
    def is_transfer(self) -> bool:
        return self.transaction_type in [self.TransactionType.TRANSFER_IN, self.TransactionType.TRANSFER_OUT]

    @property
    def is_incoming_transfer(self) -> bool:
        return self.transaction_type == self.TransactionType.TRANSFER_IN

    @property
    def is_outgoing_transfer(self) -> bool:
        return self.transaction_type == self.TransactionType.TRANSFER_OUT


class ShopItemQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ShopItem(models.Model):
    class ProductType(models.TextChoices):
        STUB = 'stub', 'Заглушка'
        SUBSCRIPTION = 'subscription', 'Подписка'
        CHANGE_USERNAME = 'change_username', 'Смена никнейма'
        CHANGE_PUBLIC_ID = 'change_public_id', 'Смена public id'

    slug = models.SlugField('Слаг', unique=True, max_length=128)
    product_type = models.CharField(
        'Тип товара', max_length=32, choices=ProductType.choices, default=ProductType.SUBSCRIPTION
    )
    name = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    price = models.DecimalField('Стоимость', max_digits=10, decimal_places=2)
    image = models.ImageField('Изображение', upload_to='shop_items/', blank=True, null=True)
    metadata = models.JSONField('Дополнительные данные', default=dict, blank=True)
    position = models.PositiveIntegerField('Порядок отображения', default=0)
    is_active = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлен', auto_now=True)

    objects = ShopItemQuerySet.as_manager()

    class Meta:
        verbose_name = 'Товар магазина'
        verbose_name_plural = 'Товары магазина'
        ordering = ['position', 'name']

    def __str__(self):
        return self.name

    @property
    def subscription_tier(self):
        if self.product_type != self.ProductType.SUBSCRIPTION:
            return None
        return (self.metadata or {}).get('tier', Subscription.TIER_1)

    @property
    def subscription_duration_in_days(self):
        if self.product_type != self.ProductType.SUBSCRIPTION:
            return None
        return (self.metadata or {}).get('duration_in_days', 30)


class ShopPurchase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='ID покупки')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shop_purchases', verbose_name='Пользователь')
    item = models.ForeignKey(ShopItem, on_delete=models.PROTECT, related_name='purchases', verbose_name='Товар')
    amount = models.DecimalField('Сумма списания', max_digits=10, decimal_places=2)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.PROTECT, related_name='shop_purchases', verbose_name='Транзакция'
    )
    metadata = models.JSONField('Детали покупки', default=dict, blank=True)
    created_at = models.DateTimeField('Дата покупки', auto_now_add=True)

    class Meta:
        verbose_name = 'Покупка'
        verbose_name_plural = 'Покупки'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.item.name} ({self.amount} CC)'
