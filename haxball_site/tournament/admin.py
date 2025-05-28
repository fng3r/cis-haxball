from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import resolve, reverse_lazy
from django.utils import timezone
from django.utils.safestring import mark_safe
from polymorphic.admin import (
    PolymorphicChildModelAdmin,
    PolymorphicInlineSupportMixin,
    PolymorphicParentModelAdmin,
    StackedPolymorphicInline,
)
from smart_selects.db_fields import ChainedForeignKey
from unfold import admin as unfold_admin
from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesCheckboxFilter,
    MultipleChoicesDropdownFilter,
    RelatedDropdownFilter,
    SingleNumericFilter,
)
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.sections import TableSection

from haxball_site.admin import UnfoldChainedSelect, UnfoldModelAdmin, UnfoldStackedInline, UnfoldTabularInline

from .models import (
    AchievementCategory,
    Achievements,
    Disqualification,
    FreeAgent,
    Goal,
    Group,
    GroupStage,
    League,
    Match,
    MatchResult,
    Nation,
    OtherEvents,
    Player,
    PlayerMatchStatistics,
    PlayerRating,
    PlayerRatingVersion,
    PlayerTransfer,
    PlayoffBracketSlotStub,
    PlayOffStage,
    Postponement,
    PostponementSlots,
    TeamRatingVersion,
    RegularStage,
    Season,
    SeasonTeamRating,
    Substitution,
    Team,
    TeamAchievement,
    TeamPenaltyPoints,
    TeamRating,
    TournamentStage,
    TourNumber,
)


@admin.register(FreeAgent)
class FreeAgentAdmin(UnfoldModelAdmin):
    list_display = ('id', 'player', 'position_main', 'description', 'is_active', 'created', 'deleted')
    list_filter = ('is_active',)
    search_fields = ('player__username',)
    ordering = ('-created',)


@admin.register(AchievementCategory)
class AchievementCategoryAdmin(UnfoldModelAdmin):
    list_display = ('id', 'title', 'description', 'order')


@admin.register(Achievements)
class AchievementsAdmin(UnfoldModelAdmin):
    list_display = ('id', 'position_number', 'display_medal', 'category',)
    list_filter = ('category', ('player', AutocompleteSelectFilter))
    list_filter_submit = True
    list_filter_sheet = False
    filter_horizontal = ('player',)
    search_fields = (
        'title__icontains',
        'description__icontains',
    )
    
    @display(description='Медаль', header=True)
    def display_medal(self, model):
        return [
            model.title,
            model.description,
            None,
            {
                'path': model.image.url,
                'squared': False,
                'borderless': True,
                'width': 48,
                'height': 48,
            }
        ]


@admin.register(TeamAchievement)
class TeamAchievementAdmin(UnfoldModelAdmin):
    list_display = ('id', 'season', 'position_number', 'display_medal', 'players_raw_list',)
    list_filter = (('season', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    list_filter_submit = True
    autocomplete_fields = ('team',)
    search_fields = (
        'title__icontains',
        'description__icontains',
    )
    ordering = ('-season__number', 'position_number')
    
    @display(description='Медаль', header=True)
    def display_medal(self, model):
        return [
            model.title,
            model.description,
            None,
            {
                'path': model.image.url,
                'squared': False,
                'borderless': True,
                'width': 48,
                'height': 48,
            }
        ]
        
        
class AchievementsInline(UnfoldTabularInline):
    model = Achievements.player.through
    extra = 0
    tab = True
    
    verbose_name = 'Медаль'
    verbose_name_plural = 'Медали'
    
    def has_change_permission(self, request, obj=None):
        return False
    
    
class TeamAchievementsInline(UnfoldTabularInline):
    model = TeamAchievement.team.through
    extra = 0
    tab = True
    
    verbose_name = 'Медаль'
    verbose_name_plural = 'Медали'
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Player)
class PlayerAdmin(UnfoldModelAdmin):
    list_display = (
        'name',
        'nickname',
        'team',
        'player_nation',
    )
    autocomplete_fields = ('name',)
    list_filter = (('team', RelatedDropdownFilter), ('name', RelatedDropdownFilter), ('player_nation', RelatedDropdownFilter))
    list_filter_submit = True
    search_fields = (
        'nickname',
        'name__username',
    )
    exclude = ('position',)
    inlines = [AchievementsInline]
    
    def get_readonly_fields(self, request, obj=None):
        if obj: # This is the case when object is already created
            return ['name']
        
        return []
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('name', 'team', 'player_nation')


@admin.register(PlayerTransfer)
class PlayerTransferAdmin(UnfoldModelAdmin):
    list_display = ('trans_player', 'display_from_team', 'display_to_team', 'date_join', 'season_join', 'is_technical')
    list_filter = (
        ('trans_player', RelatedDropdownFilter),
        ('from_team', RelatedDropdownFilter),
        ('to_team', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = (
        'trans_player__nickname',
        'from_team__title',
        'to_team__title',
    )
    readonly_fields = ('is_technical',)
    raw_id_fields = ('trans_player',)
    ordering = (
        '-date_join',
        '-id',
    )
    
    @display(description='Из команды', header=True)
    def display_from_team(self, model):
        if not model.from_team:
            return ['Свободный агент']
        
        return [
            model.from_team,
            None,
            None,
            {
                'path': model.from_team.logo.url,
                'squared': True,
                'borderless': True,
                'width': 24,
                'height': 24,
            }
        ]
        
    @display(description='В команду', header=True)
    def display_to_team(self, model):
        if not model.to_team:
            return ['Свободный агент']
        
        return [
            model.to_team,
            None,
            None,
            {
                'path': model.to_team.logo.url,
                'squared': True,
                'borderless': True,
                'width': 24,
                'height': 24,
            }
        ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'from_team' or db_field.name == 'to_team':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('trans_player', 'from_team', 'to_team', 'season_join')


class PlayerInline(UnfoldTabularInline):
    model = Player
    exclude = ('position',)
    tab = True
    
    def has_add_permission(self, request, obj):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Team)
class TeamAdmin(UnfoldModelAdmin):
    list_display = (
        'display_title',
        'owner',
        'date_found',
    )
    list_filter = (('owner', RelatedDropdownFilter),)
    list_filter_submit = True
    list_filter_sheet = False
    show_facets = False
    search_fields = ('title', 'short_title')
    inlines = [PlayerInline, TeamAchievementsInline]
    ordering = ['-date_found', '-id']
    
    @display(description='Команда', header=True)
    def display_title(self, model):
        return [
            model.title,
            model.short_title,
            None,
            {
                'path': model.logo.url,
                'squared': True,
                'borderless': True,
                'width': 32,
                'height': 32,
            }
        ]
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        team = None
        if 'object_id' in resolved.kwargs:
            team = Team.objects.filter(pk=resolved.kwargs['object_id']).first()
        if team and (db_field.name == 'captain' or db_field.name == 'captain_assistant'):
            kwargs['queryset'] = team.players_in_team.all()
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Season)
class SeasonAdmin(UnfoldModelAdmin):
    list_display = ('number', 'title', 'short_title', 'is_active', 'created')


@admin.register(Nation)
class NationAdmin(UnfoldModelAdmin):
    list_display = ('display_country',)
    search_fields = ('country',)
    
    @display(description='Страна', header=True, ordering='country')
    def display_country(self, model):
        return [
            model.country,
            None,
            None,
            {
                'path': model.flag.url,
                'squared': False,
                'borderless': True,
                'width': 32,
                'height': 32,
            }
        ]


@admin.register(Disqualification)
class DisqualificationAdmin(UnfoldModelAdmin):
    list_display = ('match', 'team', 'player', 'reason', 'get_tours', 'get_lifted_tours', 'created')
    list_filter = (('match__league', RelatedDropdownFilter), ('team', RelatedDropdownFilter), ('player', RelatedDropdownFilter))
    list_filter_submit = True
    list_fullwidth = True
    search_fields = ('player__nickname',)
    raw_id_fields = ('match',)
    filter_horizontal = ('tours', 'lifted_tours')

    @display(description='Туры')
    def get_tours(self, model):
        return mark_safe('<br>'.join(map(lambda t: str(t), model.tours.all())))

    @display(description='Отмененные туры')
    def get_lifted_tours(self, model):
        return mark_safe('<br>'.join(map(lambda t: str(t), model.lifted_tours.all())))

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        disqualification = None
        if 'object_id' in resolved.kwargs:
            disqualification = Disqualification.objects.filter(pk=resolved.kwargs['object_id']).first()

        if db_field.name == 'tours':
            kwargs['queryset'] = TourNumber.objects.filter(league__championship__is_active=True).order_by('number')
        elif db_field.name == 'lifted_tours':
            if disqualification:
                kwargs['queryset'] = disqualification.tours.all()
            else:
                TourNumber.objects.filter(league__championship__is_active=True).order_by('number')
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour', 'team', 'player')
            .prefetch_related('tours__league', 'tours__stage', 'lifted_tours__league', 'lifted_tours__stage')
        )


class AlwaysChangedModelForm(forms.ModelForm):
    def has_changed(self):
        """Should returns True if data differs from initial.
        By always returning true even unchanged inlines will get validated and saved."""
        return True


class PostponementSlotsInline(UnfoldTabularInline):
    model = PostponementSlots
    form = AlwaysChangedModelForm
    min_num = 1
    max_num = 1

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Postponement)
class PostponementAdmin(UnfoldModelAdmin):
    list_display = (
        'match',
        'is_emergency',
        'display_teams',
        'starts_at',
        'ends_at',
        'taken_at',
        'taken_by',
        'display_is_cancelled',
        'cancelled_at',
        'cancelled_by',
    )
    filter_horizontal = ('teams',)
    raw_id_fields = ('match',)
    autocomplete_fields = ('taken_by', 'cancelled_by')
    list_filter = (
        ('match__league', RelatedDropdownFilter),
        ('teams', RelatedDropdownFilter),
        ('taken_by', AutocompleteSelectFilter),
        'is_emergency'
    )
    list_filter_submit = True
    list_fullwidth = True
    search_fields = ('match__team_home__title', 'match__team_guest__title')
    
    fields = (
        ('match',),
        ('is_emergency',),
        ('teams',),
        ('starts_at', 'ends_at'),
        ('taken_at', 'taken_by'),
        ('cancelled_at', 'cancelled_by')
    )
    
    actions_detail = ['cancel_postponement']

    @display(description='На кого взят перенос')
    def display_teams(self, model):
        return mark_safe('<br>'.join(map(lambda t: str(t), model.teams.all())))

    @display(description='Отменен', boolean=True)
    def display_is_cancelled(self, model):
        return model.is_cancelled
    
    @action(description=('Отменить перенос'), variant=ActionVariant.DANGER, icon='cancel')
    def cancel_postponement(self, request, object_id):
        postponement = Postponement.objects.get(pk=object_id)
        if (postponement.is_cancelled):
            messages.warning(request, 'Выбранный перенос уже был отменен ранее')
            return redirect(reverse_lazy('admin:tournament_postponement_change', args=[object_id]))

        postponement.cancelled_at = timezone.now()
        postponement.cancelled_by = request.user
        postponement.save(update_fields=['cancelled_at', 'cancelled_by'])
        
        messages.success(
            request, "Перенос успешно отменен"
        )
        return redirect(reverse_lazy('admin:tournament_postponement_change', args=[object_id]))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'match':
            kwargs['queryset'] = Match.objects.filter(league__championship__is_active=True).order_by(
                'numb_tour__number'
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'teams':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct()
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related(
                'match', 'match__team_home', 'match__team_guest', 'match__numb_tour',
                'taken_by', 'cancelled_by',
            )
            .prefetch_related('teams')
        )


class TournamentStageInline(StackedPolymorphicInline, UnfoldStackedInline):
    class RegularStageInline(StackedPolymorphicInline.Child, UnfoldStackedInline):
        model = RegularStage
        exclude = ('type', 'postponable',)
        filter_horizontal = ('teams',)

    class GroupStageInline(StackedPolymorphicInline.Child, UnfoldStackedInline):
        model = GroupStage
        exclude = ('type', 'postponable',)
        filter_horizontal = ('teams',)

    class PlayOffStageInline(StackedPolymorphicInline.Child, UnfoldStackedInline):
        model = PlayOffStage
        exclude = ('type', 'postponable', 'use_buchholz')
        filter_horizontal = ('teams',)

    model = TournamentStage
    child_inlines = (
        RegularStageInline,
        GroupStageInline,
        PlayOffStageInline,
    )
    ordering_field = 'type'
    
    def has_delete_permission(self, request, obj=None):
        return False


class GroupInline(UnfoldStackedInline):
    model = Group
    tab = True
    extra = 1
    fields = ('stage', 'name', 'teams')
    filter_horizontal = ('teams',)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        stage = None
        if 'object_id' in resolved.kwargs:
            stage = self.parent_model.objects.filter(pk=resolved.kwargs['object_id']).first()

        if db_field.name == 'teams' and stage is not None:
            kwargs['queryset'] = stage.teams if stage.teams.exists() else stage.league.teams
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    
class TeamPenaltyPointsInline(UnfoldStackedInline):
    model = TeamPenaltyPoints
    extra = 1
    tab = True
    fields = (
        ('team', 'penalty_points'),
    )
    
    
class TourInline(UnfoldStackedInline):
    model = TourNumber
    extra = 1
    tab = True
    
    fields = (
        ('number', 'name'),
        ('date_from', 'date_to'),
        ('bracket', 'league')
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path)
        stage = None
        if 'object_id' in resolved.kwargs:
            stage = TournamentStage.objects.filter(pk=resolved.kwargs['object_id']).first()
            
        if db_field.name == 'league' and stage is not None:
            kwargs['queryset'] = League.objects.filter(id__in=[stage.league.id])
            formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
            formfield.initial = stage.league
            return formfield
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TournamentStage)
class TournamentStageAdmin(PolymorphicParentModelAdmin, UnfoldModelAdmin):
    base_model = TournamentStage
    child_models = [RegularStage, GroupStage, PlayOffStage]
    list_filter = (('league', RelatedDropdownFilter), ('type', ChoicesCheckboxFilter),)
    list_filter_submit = True
    list_display = ('get_stage_name', 'league', 'order', 'postponable',)
    list_display_links = ('get_stage_name',)
    list_editable = ('postponable',)

    @display(description='Этап')
    def get_stage_name(self, model):
        return model.stage_name


class TournamentStageChildBase(PolymorphicChildModelAdmin, UnfoldModelAdmin):
    show_in_index = False
    exclude = ('type',)
    readonly_fields = ('league',)
    filter_horizontal = ('teams',)
    
    def get_readonly_fields(self, request, obj=None):
        if obj: # This is the case when object is already created
            return ['type', 'league']
        
        return []

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        stage = None
        if 'object_id' in resolved.kwargs:
            stage = TournamentStage.objects.filter(pk=resolved.kwargs['object_id']).first()

        if db_field.name == 'teams' and stage is not None:
            kwargs['queryset'] = stage.league.teams
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(RegularStage)
class RegularStageAdmin(TournamentStageChildBase):
   inlines = [TourInline, TeamPenaltyPointsInline]


@admin.register(GroupStage)
class GroupStageAdmin(TournamentStageChildBase):
    inlines = [GroupInline, TourInline, TeamPenaltyPointsInline]


class PlayoffBracketSlotStubInline(UnfoldStackedInline):
    model = PlayoffBracketSlotStub
    extra = 1
    tab = True
    
    fields = (
        ('tour', 'slot'),
        ('top_team', 'top_team_placeholder'),
        ('bottom_team', 'bottom_team_placeholder')
    )
    

@admin.register(PlayOffStage)
class PlayOffStageAdmin(TournamentStageChildBase):
    inlines = [TourInline, PlayoffBracketSlotStubInline]
    exclude = ('use_buchholz',)


@admin.register(League)
class LeagueAdmin(PolymorphicInlineSupportMixin, UnfoldModelAdmin):
    list_display = ('title', 'slug', 'priority', 'championship', 'created', 'logo')
    list_filter = (('championship', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('title',)
    filter_horizontal = ('teams',)
    inlines = [PostponementSlotsInline, TournamentStageInline]


class GoalInline(UnfoldStackedInline):
    model = Goal
    extra = 1
    tab = True
    
    fields = (
        ('team', 'author', 'assistent',),
        ('time_min', 'time_sec',),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        match = None
        if 'object_id' in resolved.kwargs:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        if db_field.name == 'team' and match is not None:
            kwargs['queryset'] = Team.objects.filter(id__in=[match.team_home.id, match.team_guest.id])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SubstitutionInline(UnfoldStackedInline):
    model = Substitution
    extra = 1
    tab = True
    
    fields = (
        ('team', 'player_out', 'player_in'),
        ('time_min', 'time_sec'),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        not_found = False
        try:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == 'team' and not not_found:
            kwargs['queryset'] = Team.objects.filter(Q(home_matches=match) | Q(guest_matches=match)).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class DisqualificationInline(UnfoldStackedInline):
    model = Disqualification
    extra = 1
    tab = True
    filter_horizontal = ('tours',)
    
    fields = (
        ('team', 'player'),
        ('reason',),
        ('tours',),
    )
    exclude = ('lifted_tours',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'team':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'tours':
            kwargs['queryset'] = TourNumber.objects.filter(league__championship__is_active=True).order_by('number')
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class EventInline(UnfoldStackedInline):
    model = OtherEvents
    extra = 1
    tab = True
    
    fields = (
        ('team', 'author'),
        ('time_min', 'time_sec'),
        ('event',),
        ('card_reason',)
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        not_found = False
        try:
            self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == 'team' and not not_found:
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class MatchResultInline(UnfoldTabularInline):
    model = MatchResult
    readonly_fields = ['winner']
    can_delete = False


class PosponementInline(UnfoldStackedInline):
    model = Postponement
    extra = 0
    tab = True
    
    fields = (
        ('is_emergency',),
        ('teams',),
        ('starts_at', 'ends_at'),
        ('taken_at', 'taken_by'),
        ('cancelled_at', 'cancelled_by')
    )
    filter_horizontal = ('teams',)
    
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        match = None
        if 'object_id' in resolved.kwargs:
            match = self.parent_model.objects.filter(id=resolved.kwargs['object_id']).first()
        
        if db_field.name == 'teams' and match is not None:
            kwargs['queryset'] = Team.objects.filter(Q(home_matches=match) | Q(guest_matches=match)).distinct()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

@admin.register(Match)
class MatchAdmin(UnfoldModelAdmin):
    list_display = (
        'league',
        'display_stage',
        'display_tour',
        'group',
        'bracket_slot',
        'display_team_home',
        'score_home',
        'display_team_guest',
        'score_guest',
        'is_played',
        'result',
        'updated',
        'inspector',
        'id',
    )
    list_editable = ('bracket_slot', 'is_played')
    
    @display(description='Этап', ordering='stage__order')
    def display_stage(self, model):
        return model.stage.stage_name

    @display(description='Тур', ordering='numb_tour__number')
    def display_tour(self, model):
        tour = model.numb_tour
        bracket_postfix = (
            f', {tour.get_bracket_display()}'
            if model.league.is_multistage_league() and tour.bracket is not None
            else ''
        )
        return f'{model.numb_tour.number} тур{bracket_postfix}'
    
    @display(description='Хозяева', header=True)
    def display_team_home(self, model):
        return [
            model.team_home,
            None,
            None,
            {
                'path': model.team_home.logo.url,
                'squared': True,
                'borderless': True,
                'width': 24,
                'height': 24,
            }
        ]
        
    @display(description='Гости', header=True)
    def display_team_guest(self, model):
        return [
            model.team_guest,
            None,
            None,
            {
                'path': model.team_guest.logo.url,
                'squared': True,
                'borderless': True,
                'width': 24,
                'height': 24,
            }
        ]

    search_fields = ('team_home__title', 'team_guest__title')
    filter_horizontal = (
        'team_home_start',
        'team_guest_start',
    )

    list_filter = (
        ('league', RelatedDropdownFilter),
        ('stage', RelatedDropdownFilter),
        ('numb_tour__number', SingleNumericFilter),
        ('inspector', RelatedDropdownFilter),
        'is_played',
        ('result__value', ChoicesCheckboxFilter)
    )
    list_filter_submit = True
    list_fullwidth = True
    
    fieldsets = (
        (
            'Основная инфа',
            {
                'fields': (
                    ('league', 'stage', 'numb_tour'),
                    ('group', 'bracket_slot'),
                    ('team_home', 'team_guest', ),
                    ('score_home', 'score_guest'),
                )
            },
        ),
        (
            None,
            {
                'fields': (
                    ('is_played',),
                    ('match_date',),
                    ('inspector', 'replay_link', 'replay_link_second')
                )
            },
        ),
        (
            'Составы',
            {
                'classes': ('collapse',),
                'fields': ('team_home_start', 'team_guest_start'),
            },
        ),
        (
            'Комментарий',
            {
                'classes': ('collapse',),
                'fields': ('comment',),
            }
        ),
    )
    inlines = [
        MatchResultInline,
        GoalInline,
        SubstitutionInline,
        EventInline,
        DisqualificationInline
    ]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Берём из пути id матча
        resolved = resolve(request.path_info)

        if db_field.name == 'team_home_start':
            # Игроки команды хозяев
            team = Team.objects.filter(home_matches=resolved.kwargs.get('object_id')).first()
            kwargs['queryset'] = Player.objects.filter(team=team)
        if db_field.name == 'team_guest_start':
            # Игроки команды гостей
            team = Team.objects.filter(guest_matches=resolved.kwargs.get('object_id')).first()
            kwargs['queryset'] = Player.objects.filter(team=team)
        return super().formfield_for_manytomany(db_field, request, **kwargs)
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related(
                'team_home', 'team_guest', 'numb_tour', 'league', 'league__championship',
                'stage', 'group', 'result', 'inspector'
            )
        )


@admin.register(Goal)
class GoalAdmin(UnfoldModelAdmin):
    list_display = ('match', 'author', 'assistent',)
    ordering = ('-id',)
    raw_id_fields = ('match',)
    list_filter = (('author', RelatedDropdownFilter), ('assistent', RelatedDropdownFilter))
    list_filter_submit = True
    list_filter_sheet = False
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related(
                'author', 'assistent',
                'match__team_home', 'match__team_guest', 'match__numb_tour'
            )
        )


@admin.register(Substitution)
class SubstitutionAdmin(UnfoldModelAdmin):
    list_display = ('match', 'team', 'player_out', 'player_in')
    ordering = ('-id',)
    raw_id_fields = ('match',)
    list_filter = (
        ('team', RelatedDropdownFilter),
        ('player_out', RelatedDropdownFilter),
        ('player_in', RelatedDropdownFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related(
                'team', 'player_out', 'player_in',
                'match__team_home', 'match__team_guest', 'match__numb_tour'
            )
        )


@admin.register(OtherEvents)
class OtherEventsAdmin(UnfoldModelAdmin):
    list_display = (
        'id',
        'event',
        'match',
        'author',
        'team',
    )
    ordering = ('-id',)
    raw_id_fields = ('match',)
    list_filter = (
        ('event', MultipleChoicesDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related(
                'team', 'author',
                'match__team_home', 'match__team_guest', 'match__numb_tour'
            )
        )
    
    
class MatchInline(unfold_admin.StackedInline):
    model = Match
    extra = 0
    tab = True
    
    fields = (
        ('league', 'stage'),
        ('team_home', 'team_guest'),
        ('group', 'bracket_slot'),
    )
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # override chained selects behavior for fields which should be prefilled with inferred data
        if db_field.name == 'league' or db_field.name == 'stage':
            resolved = resolve(request.path)
            tour = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
            
            if db_field.name == 'league':
                kwargs['queryset'] = League.objects.filter(id__in=[tour.league.id])
                formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
                formfield.initial = tour.league
            if db_field.name == 'stage':
                kwargs['queryset'] = TournamentStage.objects.filter(id__in=[tour.stage.id])
                formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
                formfield.initial = tour.stage
                
            return formfield
        
        if isinstance(db_field, ChainedForeignKey):
            widget = UnfoldChainedSelect(
                to_app_name=db_field.to_app_name,
                to_model_name=db_field.to_model_name,
                chained_field=db_field.chained_field,
                chained_model_field=db_field.chained_model_field,
                foreign_key_app_name=db_field.model._meta.app_label,
                foreign_key_model_name=db_field.model._meta.object_name,
                foreign_key_field_name=db_field.name,
                show_all=db_field.show_all,
                auto_choose=db_field.auto_choose,
                sort = db_field.sort,
                view_name=db_field.view_name
            )
            kwargs['widget'] = widget
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
    def has_delete_permission(self, request, obj=None):
        return False

    
    
class MatchesTableSection(TableSection):
    related_name = 'tour_matches'
    fields = [
        'team_home',
        'team_guest',
        'display_result'
    ]
    
    @display(description='Результат')
    def display_result(self, model):
        if model.is_played:
            return model.result
        
        return '-'


@admin.register(TourNumber)
class TourAdmin(UnfoldModelAdmin):
    list_display = ('number', 'league', 'stage', 'bracket', 'date_from', 'date_to', 'is_actual')
    list_filter = (
        ('league', RelatedDropdownFilter),
        ('stage', RelatedDropdownFilter),
        ('number', SingleNumericFilter),
    )
    list_filter_submit = True
    
    inlines = [MatchInline]
    list_sections = [MatchesTableSection]

    @display(description='Актуальный', boolean=True)
    def is_actual(self, model):
        return model.is_actual
    
    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('league__championship', 'stage__league')
            .prefetch_related('tour_matches__team_home', 'tour_matches__team_guest', 'tour_matches__result')
        )


@admin.register(SeasonTeamRating)
class SeasonTeamRatingAdmin(UnfoldModelAdmin):
    list_display = ('season', 'team', 'points_for_matches', 'points_for_result', 'total_points')
    list_filter = (('season', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    list_filter_submit = True


@admin.register(TeamRatingVersion)
class TeamRatingVersionAdmin(UnfoldModelAdmin):
    list_display = ('number', 'date', 'related_season')


@admin.register(TeamRating)
class TeamRatingAdmin(UnfoldModelAdmin):
    list_display = ('version', 'rank', 'team', 'total_points')
    list_filter = (('version', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    list_filter_submit = True


@admin.register(PlayerMatchStatistics)
class PlayerMatchStatisticsAdmin(UnfoldModelAdmin):
    list_display = ('player', 'match', 'team', 'league')
    list_filter = (('player', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    list_filter_submit = True


@admin.register(PlayerRatingVersion)
class PlayerRatingVersionAdmin(UnfoldModelAdmin):
    list_display = ('number', 'date')


@admin.register(PlayerRating)
class PlayerRatingAdmin(UnfoldModelAdmin):
    list_display = ('player', 'rating_points', 'grade', 'version')
    list_filter = (
        ('version', RelatedDropdownFilter),
        ('player', RelatedDropdownFilter),
        ('grade', ChoicesCheckboxFilter)
    )
    list_filter_submit = True
    list_filter_sheet = False