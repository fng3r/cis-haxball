from django.contrib import admin

from unfold import admin as unfold_admin
from unfold.contrib.filters.admin import RelatedDropdownFilter

from .models import FantasyTournament, SquadPlayer, SquadSubmission


@admin.register(FantasyTournament)
class FantasyTournamentAdmin(unfold_admin.ModelAdmin):
    list_display = ('league', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('league__title',)


@admin.register(SquadPlayer)
class SquadPlayerAdmin(unfold_admin.ModelAdmin):
    list_display = ('player', 'position')
    list_filter = ('position',)
    search_fields = ('player__nickname',)


@admin.register(SquadSubmission)
class SquadSubmissionAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'tour', 'tournament', 'created', 'updated')
    list_filter = (('tournament', RelatedDropdownFilter), ('tour', RelatedDropdownFilter), 'created')
    search_fields = ('user__username',)
    readonly_fields = ('created', 'updated')
    filter_horizontal = ('primary_squad', 'secondary_squad')

    fieldsets = (
        ('Основная информация', {'fields': ('user', 'tour', 'tournament', 'created', 'updated')}),
        ('Выбранные составы', {'fields': ('primary_squad', 'secondary_squad')}),
    )
