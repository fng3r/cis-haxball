from django.contrib import admin
from django.forms import ModelForm, ValidationError
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesCheckboxFilter, RangeNumericFilter, RelatedDropdownFilter

from balance.services import BalanceService

from .models import Balance, Transaction


@admin.register(Balance)
class BalanceAdmin(ModelAdmin):
    list_display = ['user', 'current_balance', 'updated_at']
    list_filter = [('user', RelatedDropdownFilter), ('current_balance', RangeNumericFilter)]
    list_filter_submit = True
    list_filter_sheet = False
    search_fields = ['user__username']
    readonly_fields = ['user', 'current_balance', 'created_at', 'updated_at']
    ordering = ['-updated_at']

    fieldsets = (
        (_('Основная информация'), {'fields': ('user', 'current_balance')}),
        (
            _('Системная информация'),
            {
                'fields': ('created_at', 'updated_at'),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TransactionAdminForm(ModelForm):
    class Meta:
        model = Transaction
        fields = ['user', 'transaction_type', 'amount', 'description', 'admin_user', 'related_user']

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user')
        transaction_type = cleaned_data.get('transaction_type')
        amount = cleaned_data.get('amount')

        if not all([user, transaction_type, amount]):
            return cleaned_data

        if transaction_type in [
            Transaction.TransactionType.TRANSFER_IN,
            Transaction.TransactionType.TRANSFER_OUT,
        ]:
            raise ValidationError('Переводы не могут быть созданы через админку')

        if transaction_type in [Transaction.TransactionType.WITHDRAWAL, Transaction.TransactionType.TRANSFER_OUT]:
            balance = Balance.objects.get_user_balance(user)
            if balance < amount:
                raise ValidationError(f'Недостаточно средств на балансе. Доступно: {balance}, требуется: {amount}')

        return cleaned_data

    def save(self, commit=True):
        """Override save to use service layer"""
        transaction_obj = super().save(commit=False)
        user = transaction_obj.user
        amount = transaction_obj.amount
        description = transaction_obj.description
        admin_user = transaction_obj.admin_user

        if transaction_obj.transaction_type == Transaction.TransactionType.DEPOSIT:
            return BalanceService.add_coins(user, amount, description, admin_user)
        if transaction_obj.transaction_type == Transaction.TransactionType.WITHDRAWAL:
            return BalanceService.subtract_coins(user, amount, description, admin_user)
        raise ValidationError('Invalid transaction type')


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    form = TransactionAdminForm
    list_display = [
        'id',
        'user',
        'transaction_type',
        'amount',
        'description',
        'balance_before',
        'balance_after',
        'admin_user',
        'created_at',
    ]
    list_filter = [
        ('user', RelatedDropdownFilter),
        ('transaction_type', ChoicesCheckboxFilter),
        ('admin_user', RelatedDropdownFilter),
    ]
    list_filter_submit = True
    search_fields = ['user__username', 'user__email', 'description', 'admin_user__username']
    readonly_fields = ['id', 'balance_before', 'balance_after', 'created_at']
    ordering = ['-created_at']

    fieldsets = (
        (_('Основная информация'), {'fields': ('user', 'transaction_type', 'amount', 'description')}),
        (_('Административная информация'), {'fields': ('admin_user', 'related_user')}),
        (_('Баланс'), {'fields': ('balance_before', 'balance_after')}),
        (_('Системная информация'), {'fields': ('id', 'created_at'), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        """Оптимизация запросов"""
        return super().get_queryset(request).select_related('user', 'admin_user', 'related_user')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
