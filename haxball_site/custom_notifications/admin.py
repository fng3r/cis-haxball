from django.contrib import admin
from notifications.models import Notification
from unfold.contrib.filters.admin import RelatedDropdownFilter

from haxball_site.admin import UnfoldModelAdmin

# Register your models here.

admin.site.unregister(Notification)

@admin.register(Notification)
class NotificationAdmin(UnfoldModelAdmin):
    list_display = ('recipient', 'actor', 'level', 'target', 'timestamp', 'unread')
    list_filter = (
        ('recipient', RelatedDropdownFilter),
        'timestamp',
        'unread',
        'level',
    )
    list_filter_submit = True
    list_filter_sheet = False