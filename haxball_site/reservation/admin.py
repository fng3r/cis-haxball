from django.contrib import admin

from .models import Replay, ReservationEntry, ReservationHost

# Register your models here.

admin.site.register(Replay)


@admin.register(ReservationHost)
class ReservationHostAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')


@admin.register(ReservationEntry)
class ReservationEntryAdmin(admin.ModelAdmin):
    list_display = ('author', 'match', 'time_date', 'host', 'created')
    raw_id_fields = ('match',)
    list_filter = ('host', 'author')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'host':
            kwargs['queryset'] = ReservationHost.objects.filter(is_active=True)
        return super(ReservationEntryAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
