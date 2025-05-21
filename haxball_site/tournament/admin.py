from django import forms
from django.contrib import admin
from django.db.models import Q
from django.urls import resolve
from django.utils.safestring import mark_safe
from polymorphic.admin import (
    PolymorphicChildModelAdmin,
    PolymorphicInlineSupportMixin,
    PolymorphicParentModelAdmin,
    StackedPolymorphicInline
)

from unfold.contrib.filters.admin import (
    AutocompleteSelectFilter,
    ChoicesCheckboxFilter,
    MultipleChoicesDropdownFilter,
    RelatedDropdownFilter,
    SingleNumericFilter,
)
from unfold.decorators import display

from haxball_site.admin import UnfoldModelAdmin, UnfoldStackedInline, UnfoldTabularInline

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
    PlayerTransfer,
    PlayoffBracketSlotStub,
    PlayOffStage,
    Postponement,
    PostponementSlots,
    RatingVersion,
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
    list_display = ('id', 'position_number', 'title', 'description', 'category', 'image', 'mini_image')
    list_filter = ('category',)
    filter_horizontal = ('player',)
    search_fields = (
        'title__icontains',
        'description__icontains',
    )


@admin.register(TeamAchievement)
class TeamAchievementAdmin(UnfoldModelAdmin):
    list_display = ('id', 'season', 'title', 'description', 'players_raw_list', 'position_number', 'image')
    list_filter = (('season', RelatedDropdownFilter),)
    list_filter_submit = True
    autocomplete_fields = ('team',)
    search_fields = (
        'title__icontains',
        'description__icontains',
    )


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
    
    def get_readonly_fields(self, request, obj=None):
        if obj: # This is the case when object is already created
            return ['name']
        
        return []


@admin.register(PlayerTransfer)
class PlayerTransferAdmin(UnfoldModelAdmin):
    list_display = ('trans_player', 'from_team', 'to_team', 'date_join', 'season_join', 'is_technical')
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'from_team' or db_field.name == 'to_team':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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
        'title',
        'short_title',
        'owner',
    )
    
    list_filter = (('owner', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('title',)
    inlines = [PlayerInline]
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        team = None
        if 'object_id' in resolved.kwargs:
            team = Team.objects.filter(pk=resolved.kwargs['object_id']).first()
        if team and (db_field.name == 'captain' or db_field.name == 'captain_assistant'):
            kwargs['queryset'] = team.players_in_team.all()
            
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    

class TeamPenaltyPointsAdmin(UnfoldStackedInline):
    model = TeamPenaltyPoints
    extra = 1


@admin.register(Season)
class SeasonAdmin(UnfoldModelAdmin):
    list_display = ('number', 'title', 'short_title', 'is_active', 'created')


@admin.register(Nation)
class NationAdmin(UnfoldModelAdmin):
    list_display = ('country', 'flag')
    search_fields = ('country',)


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
        'get_teams',
        'starts_at',
        'ends_at',
        'taken_at',
        'taken_by',
        'is_cancelled',
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

    @display(description='На кого взят перенос')
    def get_teams(self, model):
        return mark_safe('<br>'.join(map(lambda t: str(t), model.teams.all())))

    @display(description='Отменен', boolean=True)
    def is_cancelled(self, model):
        return model.is_cancelled

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


class TournamentStageInline(StackedPolymorphicInline):
    class RegularStageInline(StackedPolymorphicInline.Child):
        model = RegularStage
        exclude = ('type', 'postponable',)
        filter_horizontal = ('teams',)

    class GroupStageInline(StackedPolymorphicInline.Child):
        model = GroupStage
        exclude = ('type', 'postponable',)
        filter_horizontal = ('teams',)

    class PlayOffStageInline(StackedPolymorphicInline.Child):
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


@admin.register(TournamentStage)
class TournamentStageAdmin(PolymorphicParentModelAdmin):
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


class TournamentStageChildBase(PolymorphicChildModelAdmin):
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
   inlines = [TeamPenaltyPointsAdmin]


@admin.register(GroupStage)
class GroupStageAdmin(TournamentStageChildBase):
    inlines = [GroupInline, TeamPenaltyPointsAdmin]


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
    inlines = [PlayoffBracketSlotStubInline]
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
        not_found = False
        try:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == 'team' and not not_found:
            kwargs['queryset'] = Team.objects.filter(Q(home_matches=match) | Q(guest_matches=match)).distinct()
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
        ('lifted_tours',)
    )

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


# <select name="stage" class="border border-base-200 bg-white font-medium min-w-20 placeholder-base-400 rounded-default shadow-xs text-font-default-light text-sm focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 group-[.errors]:border-red-600 focus:group-[.errors]:outline-red-600 dark:bg-base-900 dark:border-base-700 dark:text-font-default-dark dark:group-[.errors]:border-red-500 dark:focus:group-[.errors]:outline-red-500 dark:scheme-dark group-[.primary]:border-transparent px-3 py-2 w-full pr-8 max-w-2xl appearance-none chained-fk" data-context="available-source" id="id_stage" data-chainfield="league" data-url="/chaining/filter/tournament/TournamentStage/league/tournament/Match/stage" data-auto_choose="false" data-empty_label="--------">
@admin.register(Match)
class MatchAdmin(UnfoldModelAdmin):
    list_display = (
        'league',
        'stage',
        'get_tour',
        'group',
        'bracket_slot',
        'team_home',
        'score_home',
        'team_guest',
        'score_guest',
        'is_played',
        'result',
        'updated',
        'inspector',
        'id',
    )
    list_editable = ('bracket_slot', 'is_played')

    @display(description='Тур', ordering='numb_tour__number')
    def get_tour(self, model):
        tour = model.numb_tour
        bracket_postfix = (
            f', {tour.get_bracket_display()}'
            if model.league.is_multistage_league() and tour.bracket is not None
            else ''
        )
        return f'{model.numb_tour.number} тур{bracket_postfix}'

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
        'is_played'
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
    inlines = [MatchResultInline, GoalInline, SubstitutionInline, EventInline, DisqualificationInline]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Берём из пути id матча
        resolved = resolve(request.path_info)

        if db_field.name == 'team_home_start':
            # Игроки команды хозяев
            t = Team.objects.filter(home_matches=resolved.kwargs.get('object_id')).first()
            kwargs['queryset'] = Player.objects.filter(team=t)
        if db_field.name == 'team_guest_start':
            # Игроки команды гостей
            t = Team.objects.filter(guest_matches=resolved.kwargs.get('object_id')).first()
            kwargs['queryset'] = Player.objects.filter(team=t)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(Goal)
class GoalAdmin(UnfoldModelAdmin):
    list_display = ('match', 'author', 'assistent', 'id')


@admin.register(Substitution)
class SubstitutionAdmin(UnfoldModelAdmin):
    list_display = ('match', 'team', 'player_out', 'player_in')


@admin.register(OtherEvents)
class OtherEventsAdmin(UnfoldModelAdmin):
    list_display = (
        'event',
        'match',
        'author',
        'team',
    )
    list_filter = (
        ('event', MultipleChoicesDropdownFilter),
        ('author', RelatedDropdownFilter),
        ('team', RelatedDropdownFilter)
    )
    list_filter_submit = True


@admin.register(TourNumber)
class TourAdmin(UnfoldModelAdmin):
    list_display = ('number', 'league', 'stage', 'bracket', 'date_from', 'date_to', 'is_actual')
    list_filter = (
        ('league', RelatedDropdownFilter),
        ('stage', RelatedDropdownFilter),
        ('number', SingleNumericFilter),
    )
    list_filter_submit = True

    @display(description='Актуальный', boolean=True)
    def is_actual(self, model):
        return model.is_actual


@admin.register(SeasonTeamRating)
class SeasonTeamRatingAdmin(UnfoldModelAdmin):
    list_display = ('season', 'team', 'points_for_matches', 'points_for_result', 'total_points')
    list_filter = (('season', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    list_filter_submit = True


@admin.register(RatingVersion)
class RatingVersionAdmin(UnfoldModelAdmin):
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
