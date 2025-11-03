from contextlib import suppress

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from balance.models import ShopPurchase
from balance.services import ShopService
from core.models import NewComment

from .models import ShopItem, Transaction


class BalanceView(LoginRequiredMixin, TemplateView):
    """Main balance page showing current balance and recent transactions"""

    template_name = 'balance/balance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context['current_balance'] = user.balance.current_balance

        transactions_per_page = 15
        transactions = Transaction.objects.filter(user=user).order_by('-created_at')
        paginator = Paginator(transactions, transactions_per_page)
        page_obj = paginator.get_page(1)

        context = {
            'current_balance': user.balance.current_balance,
            'transactions': page_obj.object_list,
            'has_more_transactions': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        }

        return context


class TransactionListView(LoginRequiredMixin, TemplateView):
    template_name = 'balance/partials/transaction_list.html'

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = request.user
        page = int(request.GET.get('page', 1))
        per_page = 15

        transactions = Transaction.objects.filter(user=user).order_by('-created_at')
        paginator = Paginator(transactions, per_page)
        page_obj = paginator.get_page(page)

        context = {
            'transactions': page_obj.object_list,
            'has_more_transactions': page_obj.has_next(),
            'next_page': page + 1 if page_obj.has_next() else None,
        }

        return render(request, self.template_name, context)


def _build_shop_item_context(
    item: ShopItem,
    user,
    balance_value,
):
    return {
        'item': item,
        'can_afford': balance_value >= item.price,
    }


class ShopView(LoginRequiredMixin, TemplateView):
    template_name = 'balance/shop.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        balance_value = user.balance.current_balance

        items = ShopItem.objects.active().select_related(None)
        item_contexts = [_build_shop_item_context(item=item, user=user, balance_value=balance_value) for item in items]

        context.update(
            {
                'current_balance': balance_value,
                'items': item_contexts,
                'is_htmx': False,
            }
        )

        return context


class ShopPurchaseView(LoginRequiredMixin, View):
    template_name = 'balance/partials/shop_item_list.html'

    def post(self, request: HttpRequest, slug: str) -> HttpResponse:
        user = request.user
        item = get_object_or_404(ShopItem.objects.active(), slug=slug)

        success_message = None
        error_message = None

        try:
            purchase_metadata = {}
            if item.product_type == ShopItem.ProductType.CHANGE_USERNAME:
                purchase_metadata['new_username'] = request.POST.get('new_username', '').strip()
            elif item.product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
                purchase_metadata['new_public_id'] = request.POST.get('new_public_id', '').strip()
            purchase = ShopService.purchase_item(user, item, metadata=purchase_metadata)
            success_message = _build_success_message(purchase)
            comment = None
            if purchase.metadata.get('comment_id'):
                with suppress(NewComment.DoesNotExist):
                    comment = NewComment.objects.get(id=purchase.metadata['comment_id'])

        except ValidationError as exc:
            error_message = _build_error_message(exc)

        user.balance.refresh_from_db(fields=['current_balance', 'updated_at'])
        balance_value = user.balance.current_balance

        items = ShopItem.objects.active().select_related(None)
        item_contexts = [
            _build_shop_item_context(item=shop_item, user=user, balance_value=balance_value) for shop_item in items
        ]

        list_html = render(
            request,
            self.template_name,
            {
                'items': item_contexts,
                'current_balance': balance_value,
                'is_htmx': True,
            },
        )

        response = HttpResponse(list_html.content)

        if success_message or error_message:
            messages_html = render_to_string(
                'balance/partials/shop_messages.html',
                {
                    'shop_success_message': success_message,
                    'shop_error_message': error_message,
                    'shop_comment': comment,
                },
                request=request,
            )
            response.write(f'<div id="shop-messages-container" hx-swap-oob="innerHTML">{messages_html}</div>')

        return response


def _build_success_message(purchase: ShopPurchase) -> str:
    if purchase.item.product_type == ShopItem.ProductType.SUBSCRIPTION:
        now = timezone.now()
        starts_at = timezone.datetime.fromisoformat(purchase.metadata.get('starts_at'))
        expires_at = timezone.datetime.fromisoformat(purchase.metadata.get('expires_at'))
        if starts_at > now:
            return 'Подписка продлена. Новая активация запланирована на ' + starts_at.strftime('%d.%m.%Y %H:%M')
        return f'Подписка активирована до {expires_at.strftime("%d.%m.%Y %H:%M")}'
    if purchase.item.product_type == ShopItem.ProductType.CHANGE_USERNAME:
        return 'Заявка на смену никнейма создана. Комментарий с заявкой автоматически добавлен в "Орг. раздел".'
    if purchase.item.product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
        return 'Заявка на смену public id создана. Комментарий с заявкой автоматически добавлен в "Орг. раздел".'

    return 'Покупка успешно завершена.'


def _build_error_message(error: ValidationError) -> str:
    error_message = error.messages[0] if getattr(error, 'messages', None) else str(error)
    if 'Insufficient funds' in error_message:
        error_message = 'Недостаточно средств на балансе'
    return error_message
