from django.urls import path

from . import views

app_name = 'balance'

urlpatterns = [
    path('balance', views.BalanceView.as_view(), name='balance'),
    path('transactions/', views.TransactionListView.as_view(), name='transactions'),
    path('shop/', views.ShopView.as_view(), name='shop'),
    path('shop/purchase/<slug:slug>/', views.ShopPurchaseView.as_view(), name='shop_purchase'),
]
