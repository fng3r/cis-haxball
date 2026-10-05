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

from .models import ShopCategory, ShopItem, Transaction


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


def _build_shop_groups(user, balance_value) -> list[dict]:
    """Active shop items grouped by active category (uncategorized first).

    Every active category gets a section even when it has no active items,
    so the template can render a fallback for empty categories.
    """
    groups_by_category_id: dict[int, dict] = {
        category.id: {'category': category, 'items': []}
        for category in ShopCategory.objects.filter(is_active=True)
    }

    uncategorized: list[dict] = []
    for item in ShopItem.objects.active().select_related('gift', 'category'):
        item_ctx = _build_shop_item_context(item=item, user=user, balance_value=balance_value)
        category = item.category
        if category is None or not category.is_active:
            uncategorized.append(item_ctx)
        else:
            groups_by_category_id[category.id]['items'].append(item_ctx)

    groups = []
    if uncategorized:
        groups.append({'category': None, 'items': uncategorized})
    groups.extend(
        sorted(
            groups_by_category_id.values(),
            key=lambda group: (group['category'].position, group['category'].title),
        )
    )
    return groups


PURCHASES_PER_PAGE = 10


def _get_user_purchases_page(user, page: int = 1):
    purchases = ShopPurchase.objects.filter(user=user).select_related('item__gift').order_by('-created_at')
    paginator = Paginator(purchases, PURCHASES_PER_PAGE)
    page_obj = paginator.get_page(page)
    _attach_purchase_extras(list(page_obj.object_list))
    return page_obj


def _attach_purchase_extras(purchases: list[ShopPurchase]) -> None:
    comment_ids = [purchase.metadata.get('comment_id') for purchase in purchases if purchase.metadata.get('comment_id')]
    comments_by_id: dict[int, NewComment] = {}
    if comment_ids:
        for comment in NewComment.objects.filter(id__in=comment_ids):
            comments_by_id[comment.id] = comment

    for purchase in purchases:
        purchase.details = _build_purchase_details(purchase)  # type: ignore[attr-defined]
        comment_id = purchase.metadata.get('comment_id')
        purchase.comment = comments_by_id.get(comment_id) if comment_id else None  # type: ignore[attr-defined]


def _build_purchase_details(purchase: ShopPurchase) -> str:
    metadata = purchase.metadata or {}
    product_type = purchase.item.product_type
    if product_type == ShopItem.ProductType.SUBSCRIPTION:
        expires_at_raw = metadata.get('expires_at')
        if expires_at_raw:
            try:
                expires_at = timezone.datetime.fromisoformat(expires_at_raw)
                return f'Активна до {expires_at.strftime("%d.%m.%Y %H:%M")}'
            except (ValueError, TypeError):
                pass
        return ''
    if product_type == ShopItem.ProductType.CHANGE_USERNAME:
        old_username = metadata.get('old_username')
        new_username = metadata.get('new_username')
        if old_username and new_username:
            return f'{old_username} → {new_username}'
        return str(new_username or '')
    if product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
        new_public_id = metadata.get('new_public_id')
        return f'Новый public id: {new_public_id}' if new_public_id else ''
    if product_type == ShopItem.ProductType.GIFT:
        recipient = metadata.get('recipient')
        return f'Получатель: {recipient}' if recipient else ''
    return ''


class ShopView(LoginRequiredMixin, TemplateView):
    template_name = 'balance/shop.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        balance_value = user.balance.current_balance

        groups = _build_shop_groups(user, balance_value)

        purchases_page = _get_user_purchases_page(user, page=1)

        context.update(
            {
                'current_balance': balance_value,
                'groups': groups,
                'is_htmx': False,
                'purchases': purchases_page.object_list,
                'has_more_purchases': purchases_page.has_next(),
                'next_purchases_page': purchases_page.next_page_number() if purchases_page.has_next() else None,
            }
        )

        return context


class ShopPurchaseHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'balance/partials/shop_purchase_history_list.html'

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        page = int(request.GET.get('page', 1))
        purchases_page = _get_user_purchases_page(request.user, page=page)

        context = {
            'purchases': purchases_page.object_list,
            'has_more_purchases': purchases_page.has_next(),
            'next_purchases_page': page + 1 if purchases_page.has_next() else None,
        }

        return render(request, self.template_name, context)


class ShopPurchaseView(LoginRequiredMixin, View):
    template_name = 'balance/partials/shop_item_list.html'

    def post(self, request: HttpRequest, slug: str) -> HttpResponse:
        user = request.user
        item = get_object_or_404(ShopItem.objects.active().select_related('gift'), slug=slug)

        success_message = None
        error_message = None
        comment = None

        try:
            purchase_metadata = {}
            if item.product_type == ShopItem.ProductType.CHANGE_USERNAME:
                purchase_metadata['new_username'] = request.POST.get('new_username', '').strip()
            elif item.product_type == ShopItem.ProductType.CHANGE_PUBLIC_ID:
                purchase_metadata['new_public_id'] = request.POST.get('new_public_id', '').strip()
            elif item.product_type == ShopItem.ProductType.GIFT:
                purchase_metadata['recipient_username'] = request.POST.get('recipient_username', '').strip()
                purchase_metadata['message'] = request.POST.get('message', '').strip()
            purchase = ShopService.purchase_item(user, item, metadata=purchase_metadata)
            success_message = _build_success_message(purchase)
            if purchase.metadata.get('comment_id'):
                with suppress(NewComment.DoesNotExist):
                    comment = NewComment.objects.get(id=purchase.metadata['comment_id'])

        except ValidationError as exc:
            error_message = _build_error_message(exc)

        user.balance.refresh_from_db(fields=['current_balance', 'updated_at'])
        balance_value = user.balance.current_balance

        groups = _build_shop_groups(user, balance_value)

        list_html = render(
            request,
            self.template_name,
            {
                'groups': groups,
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

        purchases_page = _get_user_purchases_page(user, page=1)
        purchases_html = render_to_string(
            'balance/partials/shop_purchase_history_list.html',
            {
                'purchases': purchases_page.object_list,
                'has_more_purchases': purchases_page.has_next(),
                'next_purchases_page': purchases_page.next_page_number() if purchases_page.has_next() else None,
            },
            request=request,
        )
        response.write(f'<div id="shop-purchases-container" hx-swap-oob="innerHTML">{purchases_html}</div>')

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
    if purchase.item.product_type == ShopItem.ProductType.GIFT:
        recipient = purchase.metadata.get('recipient')
        gift_name = purchase.item.gift.name if purchase.item.gift else purchase.item.name
        if recipient and recipient != purchase.user.username:
            return f'Подарок «{gift_name}» отправлен пользователю {recipient}.'
        return f'Подарок «{gift_name}» добавлен в вашу коллекцию.'

    return 'Покупка успешно завершена.'


def _build_error_message(error: ValidationError) -> str:
    error_message = error.messages[0] if getattr(error, 'messages', None) else str(error)
    if 'Insufficient funds' in error_message:
        error_message = 'Недостаточно средств на балансе'
    return error_message
