from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from .models import Transaction


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

        print(context)

        return render(request, self.template_name, context)
