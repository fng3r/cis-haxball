from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='all'),
    path('<int:notification_id>', views.NotificationView.as_view(), name='notification'),
    path('mark-as-read/<int:notification_id>', views.mark_as_read, name='mark_as_read'),
    path('mark-all-as-read', views.mark_all_as_read, name='mark_all_as_read'),
    path('delete/<int:notification_id>', views.delete_notification, name='delete'),
    path('badge', views.notification_badge, name='badge'),
]
