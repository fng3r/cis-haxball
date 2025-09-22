from django.contrib import admin
from django.urls import resolve

from unfold import admin as unfold_admin
from unfold.contrib.filters.admin import RelatedDropdownFilter

from tournament.models import Player

from .models import FantasyTournament, PlayerCost, SquadPlayer, SquadSubmission


@admin.register(FantasyTournament)
class FantasyTournamentAdmin(unfold_admin.ModelAdmin):
    list_display = ('league', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('league__title',)


@admin.register(SquadPlayer)
class SquadPlayerAdmin(unfold_admin.ModelAdmin):
    list_display = ('player', 'position', 'squad_type')
    list_filter = ('position',)
    search_fields = ('player__nickname',)


class SquadPlayerInline(unfold_admin.StackedInline):
    model = SquadPlayer
    extra = 0
    fields = (('squad_type', 'player', 'position'),)
    list_filter = ('position',)
    search_fields = ('player__nickname',)


@admin.register(SquadSubmission)
class SquadSubmissionAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'tour', 'tournament', 'created', 'updated')
    list_filter = (('tournament', RelatedDropdownFilter), ('tour', RelatedDropdownFilter), 'created')
    search_fields = ('user__username',)
    readonly_fields = (
        'created',
        'updated',
    )
    inlines = [SquadPlayerInline]

    fieldsets = (
        ('Основная информация', {'fields': ('user', 'tour', 'tournament', 'created', 'updated')}),
        ('Состав', {'fields': ('captain_player',)}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        if 'object_id' in resolved.kwargs:
            submission = SquadSubmission.objects.filter(pk=resolved.kwargs['object_id']).first()
            if db_field.name == 'captain_player':
                main_squad_players = SquadPlayer.objects.filter(
                    submission=submission, squad_type=SquadPlayer.SquadType.MAIN
                ).values_list('player_id', flat=True)
                kwargs['queryset'] = Player.objects.filter(id__in=main_squad_players)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PlayerCost)
class PlayerCostAdmin(unfold_admin.ModelAdmin):
    list_display = ('player', 'cost')
    list_filter = (('player', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('player__nickname',)
    ordering = ('player__nickname',)
