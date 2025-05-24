from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from unfold.contrib.filters.admin import (
    MultipleRelatedDropdownFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from haxball_site.admin import UnfoldModelAdmin

from .models import ReservationEntry, ReservationHost


@admin.register(ReservationHost)
class ReservationHostAdmin(UnfoldModelAdmin):
    list_display = ('name', 'display_codename', 'is_active')
    list_editable = ('is_active',)
    
    @display(description='Кодовое название', label=True)
    def display_codename(self, model):
        return model.codename
    
    
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
class ReservationEntryAdmin(UnfoldModelAdmin):
    list_display = (
        'match',
        'time_date',
        'display_host',
        'author',
        'created',
        'is_active',
        'cancelled_by',
        'cancelled_at'
    )
    raw_id_fields = ('match',)
    list_filter = (
        ('host', MultipleRelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
        'time_date',
        IsActiveReservationFilter
    )
    list_filter_submit = True
    list_filter_sheet = False
    show_facets = False
    
    fields = (
        ('match', 'author'),
        ('time_date', 'host',),
        ('cancelled_at', 'cancelled_by'),
    )
    
    actions_detail = ['cancel_reservation']
    
    @display(description='Хост', label=True)
    def display_host(self, model):
        return model.host.codename
    
    @display(description='Активна', boolean=True)
    def is_active(self, model):
        return not model.is_cancelled
    
    @action(description=("Отменить бронь"), variant=ActionVariant.DANGER, icon='cancel')
    def cancel_reservation(self, request, object_id):
        reservation = ReservationEntry.objects.get(pk=object_id)
        if (reservation.is_cancelled):
            messages.warning(request, 'Выбранная бронь уже была отменена ранее')
            return redirect(reverse_lazy("admin:reservation_reservationentry_change", args=[object_id]))

        reservation.cancelled_at = timezone.now()
        reservation.cancelled_by = request.user
        reservation.save(update_fields=['cancelled_at', 'cancelled_by'])
        
        messages.success(
            request, "Бронь успешно отменена"
        )
        return redirect(reverse_lazy("admin:reservation_reservationentry_change", args=[object_id]))
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'host':
            kwargs['queryset'] = ReservationHost.objects.filter(is_active=True)
        return super(ReservationEntryAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)
