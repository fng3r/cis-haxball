from django.contrib import admin

from .models import Replay, ReservationEntry, ReservationHost

admin.site.register(Replay)


@admin.register(ReservationHost)
class ReservationHostAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    
    
class IsActiveReservationFilter(admin.SimpleListFilter):
    title = 'Активна'
    parameter_name = 'is_active'

    def lookups(self, request, model_admin):
        return (
            (1, 'Да'), 
            (0, 'Нет')
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(cancelled_at__isnull=True)
        if self.value() == '0':
            return queryset.filter(cancelled_at__isnull=False)
        return queryset


@admin.register(ReservationEntry)
class ReservationEntryAdmin(admin.ModelAdmin):
    list_display = ('author', 'match', 'time_date', 'host', 'created', 'is_active', 'cancelled_at', 'cancelled_by')
    raw_id_fields = ('match',)
    list_filter = ('host', 'author', 'time_date', IsActiveReservationFilter)
    
    def is_active(self, model):
        return not model.is_cancelled
    is_active.boolean = True
    is_active.short_description = 'Активна'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'host':
            kwargs['queryset'] = ReservationHost.objects.filter(is_active=True)
        return super(ReservationEntryAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
