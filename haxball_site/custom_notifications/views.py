from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import ListView, View
from django_htmx.http import trigger_client_event
from notifications.models import Notification


class NotificationView(View):
    """Custom view for a single notification with HTMX support."""
    def get(self, request, notification_id):
        notification = get_object_or_404(Notification, id=notification_id)
        return render(
            request,
            'notifications/notifications_list.html#notification-list-item',
            {'notification': notification}
        )


class NotificationListView(ListView):
    """Custom view for listing notifications with HTMX support."""
    model = Notification
    context_object_name = 'notifications'
    paginate_by = 10
    template_name = 'notifications/all.html'
    
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        qs = self.request.user.notifications.all()
        
        # Filter by notification type if specified
        notification_type = self.request.GET.get('type')
        if notification_type == 'unread':
            qs = qs.unread()
            
        qs = qs.prefetch_related('actor', 'actor__user_profile', 'action_object', 'target')
            
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_count'] = self.request.user.notifications.count()
        context['unread_count'] = self.request.user.notifications.unread().count()
        
        return context
    
    def get_template_names(self):
        # Return different template if it's an HTMX request
        if self.request.htmx:
            return ['notifications/notification_list_partial.html']
        return [self.template_name]


@login_required
@require_POST
def mark_as_read(request, notification_id=None):
    """Mark a notification as read with HTMX support."""
    notification = get_object_or_404(Notification, recipient=request.user, id=notification_id)
    notification.mark_as_read()
    
    response = HttpResponse(status=204)
    response = trigger_client_event(response, 'unread-count-changed', {'target': '#notification-badge-counter'})
    response = trigger_client_event(response, 'notification-read', {'id': notification.id})
    return response


@login_required
@require_POST
def mark_all_as_read(request):
    """Mark all notifications as read with HTMX support."""
    request.user.notifications.unread().mark_all_as_read()

    response = HttpResponse(status=204)
    response = trigger_client_event(response, 'unread-count-changed', {'target': '#notification-badge-counter'})
    response = trigger_client_event(response, 'all-notifications-read', {})
    return response


@login_required
@require_POST
def delete_notification(request, notification_id=None):
    """Delete a notification with HTMX support."""
    notification = get_object_or_404(Notification, recipient=request.user, id=notification_id)
    was_unread = notification.unread
    notification.delete()
    
    if request.htmx:
        # Return success message or trigger removal via HTMX
        response = HttpResponse(status=204)
        response = trigger_client_event(response, 'notification-removed', {'id': notification_id, 'was_unread': was_unread})
        # Only trigger badge update if the notification was unread
        if was_unread:
            response = trigger_client_event(response, 'unread-count-changed', {'target': '#notification-badge-counter'})
        return response
    
    next_url = request.GET.get('next', reverse('notifications:all'))
    return redirect(next_url)


@login_required
def notification_badge(request):
    """Return the notification badge HTML for HTMX updates."""
    unread_count = request.user.notifications.unread().count()
    context = {'unread_count': unread_count}
    html = render_to_string('notifications/notification_badge.html', context, request)
    return HttpResponse(html)
