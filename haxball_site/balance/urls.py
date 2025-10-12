from django.urls import path

from . import views

app_name = 'balance'

urlpatterns = [
    path('', views.BalanceView.as_view(), name='balance'),
    path('transactions/', views.TransactionListView.as_view(), name='transactions'),
]
