from django.contrib import admin
from unfold import admin as unfold_admin
from unfold.contrib.filters.admin import (
    MultipleRelatedDropdownFilter,
    RelatedDropdownFilter,
)

from .models import ReservationEntry, ReservationHost


@admin.register(ReservationHost)
class ReservationHostAdmin(unfold_admin.ModelAdmin):
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
class ReservationEntryAdmin(unfold_admin.ModelAdmin):
    list_display = ('match', 'time_date', 'host', 'author', 'created', 'is_active', 'cancelled_by', 'cancelled_at')
    raw_id_fields = ('match',)
    list_filter = (
        ('host', MultipleRelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
        'time_date',
        IsActiveReservationFilter
    )
    list_filter_submit = True
    list_filter_sheet = False
    
    def is_active(self, model):
        return not model.is_cancelled
    is_active.boolean = True
    is_active.short_description = 'Активна'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'host':
            kwargs['queryset'] = ReservationHost.objects.filter(is_active=True)
        return super(ReservationEntryAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
