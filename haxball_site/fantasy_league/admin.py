from django.contrib import admin

from .models import FantasyTournament, SquadPlayer, SquadSubmission


@admin.register(FantasyTournament)
class FantasyTournamentAdmin(admin.ModelAdmin):
    list_display = ('league', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('league__title',)


@admin.register(SquadPlayer)
class SquadPlayerAdmin(admin.ModelAdmin):
    list_display = ('player', 'position')
    list_filter = ('position',)
    search_fields = ('player__nickname',)


@admin.register(SquadSubmission)
class SquadSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'tour', 'tournament', 'created', 'updated')
    list_filter = ('tournament', 'tour', 'created')
    search_fields = ('user__username', 'tour__title', 'tournament__league__title')
    readonly_fields = ('created', 'updated')

    fieldsets = (
        ('Основная информация', {'fields': ('user', 'tour', 'tournament', 'created', 'updated')}),
        ('Основной состав', {'fields': ('primary_squad',)}),
        ('Запасной состав', {'fields': ('secondary_squad',)}),
    )
