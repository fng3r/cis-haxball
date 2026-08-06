from django import forms
from django.contrib import admin, messages
from django.db import models
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import resolve, reverse_lazy
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
from unfold.contrib.forms.widgets import ArrayWidget
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.overrides import FORMFIELD_OVERRIDES
from unfold.sections import TableSection

from haxball_site.admin import UnfoldChainedSelect, UnfoldModelAdmin, UnfoldStackedInline, UnfoldTabularInline

from .forms import ShortDurationField
from .models import (
    AchievementCategory,
    Achievements,
    Award,
    AwardCampaign,
    AwardNomination,
    AwardNominee,
    AwardResult,
    AwardSubmission,
    AwardVote,
    AwardVoter,
    Card,
    CleanSheet,
    Disqualification,
    FreeAgent,
    Goal,
    Group,
    GroupStage,
    League,
    LegacyMedalMapping,
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
    MatchReplayStatsStatus,
    MatchResult,
    Medal,
    MedalCategory,
    MedalType,
    Nation,
    OtherEvents,
    Player,
    PlayerMatchStatistics,
    PlayerMedal,
    PlayerRating,
    PlayerRatingVersion,
    PlayerTransfer,
    PlayoffBracketSlotStub,
    PlayOffStage,
    Postponement,
    PostponementSlots,
    RegularStage,
    Season,
    SeasonTeamRating,
    Substitution,
    Team,
    TeamAchievement,
    TeamMedal,
    TeamPenaltyPoints,
    TeamRating,
    TeamRatingVersion,
    TournamentStage,
    TournamentWinner,
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
    list_display = ('id', 'position_number', 'display_medal', 'category')
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
            },
        ]


@admin.register(TeamAchievement)
class TeamAchievementAdmin(UnfoldModelAdmin):
    list_display = ('id', 'season', 'position_number', 'display_medal', 'players_raw_list')
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
            },
        ]


@admin.register(MedalType)
class MedalTypeAdmin(UnfoldModelAdmin):
    list_display = ('code', 'title', 'kind', 'league_type', 'place', 'nomination', 'statistic')
    list_filter = ('kind', 'league_type', 'place', 'statistic')
    list_filter_submit = True
    search_fields = ('code', 'title')
    autocomplete_fields = ('nomination',)
    ordering = ('order', 'code')
    fields = (
        ('code', 'kind'),
        'title',
        'image',
        'order',
        ('league_type', 'place'),
        'nomination',
        'statistic',
        'competition_code',
        ('threshold', 'unit'),
    )
    conditional_fields = {
        'league_type': (
            "['tournament_place', 'statistic_place', 'nomination_place', 'auxiliary_competition_place'].includes(kind)"
        ),
        'place': (
            "['tournament_place', 'statistic_place', 'nomination_place', 'auxiliary_competition_place'].includes(kind)"
        ),
        'nomination': "kind == 'nomination_place'",
        'statistic': "kind == 'statistic_place'",
        'competition_code': "kind == 'auxiliary_competition_place'",
        'threshold': "kind == 'career_milestone'",
        'unit': "kind == 'career_milestone'",
    }


class PlayerMedalInline(UnfoldTabularInline):
    model = PlayerMedal
    tab = True
    extra = 0
    fields = ('player', 'awarded_at')
    autocomplete_fields = ('player',)
    show_change_link = True
    verbose_name = 'Медаль игрока'
    verbose_name_plural = 'Игроки'


class TeamMedalInline(UnfoldTabularInline):
    model = TeamMedal
    tab = True
    extra = 0
    fields = ('team', 'players_raw_list', 'awarded_at')
    autocomplete_fields = ('team',)
    show_change_link = True
    verbose_name = 'Медаль команды'
    verbose_name_plural = 'Команды'


@admin.register(Medal)
class MedalAdmin(UnfoldModelAdmin):
    list_display = ('key', 'medal_type', 'category', 'season', 'league', 'edition', 'result_value')
    list_filter = (
        ('medal_type', RelatedDropdownFilter),
        ('category', RelatedDropdownFilter),
        ('season', RelatedDropdownFilter),
        ('league', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ('key', 'medal_type__title', 'season__title', 'edition')
    autocomplete_fields = ('medal_type', 'category', 'season', 'league')
    inlines = (PlayerMedalInline, TeamMedalInline)


@admin.register(MedalCategory)
class MedalCategoryAdmin(UnfoldModelAdmin):
    list_display = ('id', 'title', 'description', 'order')
    search_fields = ('title', 'description')
    ordering = ('order', 'id')


@admin.register(PlayerMedal)
class PlayerMedalAdmin(UnfoldModelAdmin):
    list_display = ('player', 'medal', 'awarded_at')
    list_filter = (('medal', RelatedDropdownFilter),)
    search_fields = ('player__nickname', 'medal__medal_type__title')
    autocomplete_fields = ('player', 'medal')


@admin.register(TeamMedal)
class TeamMedalAdmin(UnfoldModelAdmin):
    list_display = ('team', 'medal', 'awarded_at')
    list_filter = (('medal', RelatedDropdownFilter), ('team', RelatedDropdownFilter))
    search_fields = ('team__title', 'medal__medal_type__title')
    autocomplete_fields = ('team', 'medal')


@admin.register(LegacyMedalMapping)
class LegacyMedalMappingAdmin(UnfoldModelAdmin):
    list_display = ('source_model', 'source_id', 'medal')
    list_filter = ('source_model',)
    search_fields = ('source_id', 'medal__key', 'medal__medal_type__title')
    autocomplete_fields = ('medal',)


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


class PlayerMedalsInline(UnfoldTabularInline):
    model = PlayerMedal
    extra = 0
    tab = True
    fields = ('medal', 'awarded_at')
    raw_id_fields = ('medal',)
    show_change_link = True
    verbose_name = 'Медаль игрока'
    verbose_name_plural = 'Медали'

    def has_change_permission(self, request, obj=None):
        return False


class TeamMedalsInline(UnfoldTabularInline):
    model = TeamMedal
    extra = 0
    tab = True
    fields = ('medal', 'players_raw_list', 'awarded_at')
    raw_id_fields = ('medal',)
    show_change_link = True
    verbose_name = 'Медаль команды'
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
        'display_positions',
    )
    autocomplete_fields = ('name',)
    list_filter = (
        ('team', RelatedDropdownFilter),
        ('name', RelatedDropdownFilter),
        ('player_nation', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = (
        'nickname',
        'name__username',
    )
    inlines = [PlayerMedalsInline]

    @display(description='Позиции', label=True)
    def display_positions(self, obj):
        return obj.positions

    def get_readonly_fields(self, request, obj=None):
        if obj:  # This is the case when object is already created
            return ['name']
        return []

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('name', 'team', 'player_nation')

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        # manually add a blank choice to avoid unintentional appends of items
        # since ArrayWidget is rendered with one extra item (with value of default choice) when array is empty
        positions_choices = [(None, 'Select value')] + Player.Position.choices
        form.base_fields['positions'].widget = ArrayWidget(choices=positions_choices)
        return form


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
            },
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
            },
        ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'from_team' or db_field.name == 'to_team':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('trans_player', 'from_team', 'to_team', 'season_join')


class TeamPlayerInline(UnfoldTabularInline):
    model = Player
    tab = True
    fields = ('nickname', 'positions', 'team', 'player_nation')

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
        'captain',
        'captain_assistant',
        'date_found',
    )
    list_filter = (
        ('owner', RelatedDropdownFilter),
        ('captain', RelatedDropdownFilter),
        ('captain_assistant', RelatedDropdownFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    show_facets = False
    search_fields = ('title', 'short_title')
    inlines = [TeamPlayerInline, TeamMedalsInline]
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
            },
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
    list_display = ('number', 'title', 'short_title', 'type', 'is_active', 'created')
    list_filter = ('type',)
    search_fields = ('title', 'short_title')


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
            },
        ]


@admin.register(Disqualification)
class DisqualificationAdmin(UnfoldModelAdmin):
    list_display = ('match', 'team', 'player', 'reason', 'get_tours', 'get_lifted_tours', 'created')
    list_filter = (
        ('match__league', RelatedDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('player', RelatedDropdownFilter),
    )
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
            super()
            .get_queryset(request)
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
        'is_emergency',
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
        ('cancelled_at', 'cancelled_by'),
    )

    actions_detail = ['cancel_postponement']

    @display(description='На кого взят перенос')
    def display_teams(self, model):
        teams = list(model.teams.all())
        if len(teams) > 1:
            return 'Обоюдный'
        return teams[0]

    @display(description='Отменен', boolean=True)
    def display_is_cancelled(self, model):
        return model.is_cancelled

    @action(description='Отменить перенос', variant=ActionVariant.DANGER, icon='cancel')
    def cancel_postponement(self, request, object_id):
        postponement = Postponement.objects.get(pk=object_id)
        if postponement.is_cancelled:
            messages.warning(request, 'Выбранный перенос уже был отменен ранее')
            return redirect(reverse_lazy('admin:tournament_postponement_change', args=[object_id]))

        postponement.cancel(request.user)
        postponement.save(update_fields=['cancelled_at', 'cancelled_by'])

        messages.success(request, 'Перенос успешно отменен')
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
            super()
            .get_queryset(request)
            .select_related(
                'match',
                'match__team_home',
                'match__team_guest',
                'match__numb_tour',
                'taken_by',
                'cancelled_by',
            )
            .prefetch_related('teams')
        )


class TournamentStageInline(StackedPolymorphicInline):
    class RegularStageInline(StackedPolymorphicInline.Child, UnfoldStackedInline):
        model = RegularStage
        exclude = ('type', 'postponable')
        filter_horizontal = ('teams',)

    class GroupStageInline(StackedPolymorphicInline.Child, UnfoldStackedInline):
        model = GroupStage
        exclude = ('type', 'postponable')
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
    collapsible = False
    fields = (('team', 'penalty_points'),)


class TourInline(UnfoldStackedInline):
    model = TourNumber
    extra = 1
    tab = True

    fields = (
        ('number', 'name'),
        ('date_from', 'date_to'),
        ('bracket', 'league'),
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
    list_filter = (
        ('league', RelatedDropdownFilter),
        ('type', ChoicesCheckboxFilter),
    )
    list_filter_submit = True
    list_display = ('get_stage_name', 'league', 'order', 'postponable')
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
        if obj:  # This is the case when object is already created
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
    conditional_fields = {
        'round_robin_rounds': 'is_round_robin == true',
    }


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
        ('bottom_team', 'bottom_team_placeholder'),
    )


@admin.register(PlayOffStage)
class PlayOffStageAdmin(TournamentStageChildBase):
    inlines = [TourInline, PlayoffBracketSlotStubInline]
    exclude = ('use_buchholz',)


@admin.register(League)
class LeagueAdmin(PolymorphicInlineSupportMixin, UnfoldModelAdmin):
    list_display = ('title', 'type', 'slug', 'priority', 'championship', 'created', 'logo')
    list_filter = ('type', ('championship', RelatedDropdownFilter))
    list_filter_submit = True
    search_fields = ('title',)
    filter_horizontal = ('teams',)
    inlines = [PostponementSlotsInline, TournamentStageInline]


class GoalInline(UnfoldStackedInline):
    model = Goal
    extra = 1
    tab = True
    show_count = True

    fields = (
        ('kind',),
        ('team', 'author', 'assistent'),
        ('own_goal_team', 'own_goal_author'),
        ('time_min', 'time_sec'),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        match = None
        if 'object_id' in resolved.kwargs:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        if db_field.name in ('team', 'own_goal_team') and match is not None:
            kwargs['queryset'] = Team.objects.filter(id__in=[match.team_home.id, match.team_guest.id])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CardInline(UnfoldStackedInline):
    model = Card
    extra = 1
    tab = True
    show_count = True
    fields = (('team', 'author'), ('kind', 'reason'), ('time_min', 'time_sec'))

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'kind':
            kwargs['choices'] = [('', '---------'), *db_field.choices]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        match = None
        if 'object_id' in resolved.kwargs:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        if db_field.name == 'team' and match is not None:
            kwargs['queryset'] = Team.objects.filter(id__in=[match.team_home_id, match.team_guest_id])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CleanSheetInline(UnfoldStackedInline):
    model = CleanSheet
    extra = 1
    tab = True
    show_count = True
    fields = (('team', 'author'), ('period',))

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'period':
            kwargs['choices'] = [('', '---------'), *db_field.choices]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        match = None
        if 'object_id' in resolved.kwargs:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        if db_field.name == 'team' and match is not None:
            kwargs['queryset'] = Team.objects.filter(id__in=[match.team_home_id, match.team_guest_id])
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SubstitutionInline(UnfoldStackedInline):
    model = Substitution
    extra = 1
    tab = True
    show_count = True

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
    show_count = True
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
    verbose_name = 'Cобытие [obsolete]'
    verbose_name_plural = 'Cобытия [obsolete]'
    extra = 0
    tab = True
    show_count = True
    can_delete = False
    readonly_fields = ('team', 'author', 'time_min', 'time_sec', 'event', 'card_reason')

    fields = (
        ('team', 'author'),
        ('time_min', 'time_sec'),
        ('event',),
        ('card_reason',),
    )

    def has_add_permission(self, request, obj=None):
        return False


class MatchResultInline(UnfoldTabularInline):
    model = MatchResult
    readonly_fields = ['winner']
    can_delete = False


class PostponementInline(UnfoldStackedInline):
    model = Postponement
    extra = 0
    tab = True
    show_count = True

    fields = (
        ('is_emergency',),
        ('teams',),
        ('starts_at', 'ends_at'),
        ('taken_at', 'taken_by'),
        ('cancelled_at', 'cancelled_by'),
    )
    filter_horizontal = ('teams',)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_cancelled=False)

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
    FORMFIELD_OVERRIDES
    formfield_overrides = {
        **UnfoldModelAdmin.formfield_overrides,
        models.DurationField: {
            'form_class': ShortDurationField,
        },
    }
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
            },
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
            },
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
        ('result__value', ChoicesCheckboxFilter),
        ('id', SingleNumericFilter),
    )
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = False

    fieldsets = (
        (
            'Основная информация',
            {
                'fields': (
                    ('league', 'stage', 'numb_tour'),
                    ('group', 'bracket_slot'),
                    ('team_home', 'team_guest'),
                    ('score_home', 'score_guest'),
                )
            },
        ),
        (
            None,
            {
                'fields': (
                    ('is_played',),
                    ('match_date', 'duration'),
                    ('replays', 'inspector'),
                )
            },
        ),
        (
            'Стартовые составы',
            {
                'fields': ('team_home_start', 'team_guest_start'),
            },
        ),
        (
            'Комментарий',
            {
                'classes': ('collapse',),
                'fields': ('comment',),
            },
        ),
    )
    inlines = [
        MatchResultInline,
        GoalInline,
        SubstitutionInline,
        CleanSheetInline,
        CardInline,
        DisqualificationInline,
        PostponementInline,
        EventInline,
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
            super()
            .get_queryset(request)
            .select_related(
                'team_home',
                'team_guest',
                'numb_tour',
                'league',
                'league__championship',
                'stage',
                'group',
                'result',
                'inspector',
            )
        )


@admin.register(MatchReplayStatsStatus)
class MatchReplayStatsStatusAdmin(UnfoldModelAdmin):
    list_display = ('match_id', 'display_status', 'fetched_at', 'error_message')
    list_filter = ('status',)
    search_fields = ('match__id',)
    ordering = ('-fetched_at',)
    readonly_fields = ('match', 'fetched_at')

    @display(
        description='Статус',
        label={
            MatchReplayStatsStatus.Status.PENDING: 'warning',
            MatchReplayStatsStatus.Status.PARTIAL: 'warning',
            MatchReplayStatsStatus.Status.SUCCESS: 'success',
            MatchReplayStatsStatus.Status.FAILED: 'danger',
        },
    )
    def display_status(self, obj):
        return obj.status, obj.get_status_display()

    def has_add_permission(self, request):
        return False


@admin.register(MatchReplay)
class MatchReplayAdmin(UnfoldModelAdmin):
    list_display = ('match_id', 'match', 'display_status', 'replay_url', 'analyzer_replay_id', 'fetched_at')
    list_filter = (('match__league', RelatedDropdownFilter), 'status', ('match__id', SingleNumericFilter))
    list_filter_submit = True
    search_fields = ('match__id', 'replay_url', 'analyzer_replay_id')
    ordering = ('match_id', 'replay_url')
    raw_id_fields = ('match',)
    readonly_fields = ('replay_url', 'analyzer_replay_id', 'status', 'error_message', 'raw_stats_json', 'fetched_at')

    @display(
        description='Статус',
        label={
            MatchReplay.ReplayStatus.PENDING: 'warning',
            MatchReplay.ReplayStatus.AWAITING_STATS: 'warning',
            MatchReplay.ReplayStatus.READY: 'success',
            MatchReplay.ReplayStatus.FAILED: 'danger',
        },
    )
    def display_status(self, obj):
        return obj.status, obj.get_status_display()


@admin.register(MatchReplayStats)
class MatchReplayStatsAdmin(UnfoldModelAdmin):
    list_display = (
        'match_id',
        'match',
        'match_replay',
        'part_label',
        'part_order',
        'red_is_home',
        'score_red',
        'score_blue',
        'minutes',
        'poss_red',
        'poss_blue',
    )
    list_filter = (('match__league', RelatedDropdownFilter), ('match__id', SingleNumericFilter))
    list_filter_submit = True
    search_fields = ('match__id', 'match_replay__replay_url', 'match_replay__analyzer_replay_id')
    ordering = ('match_id', 'part_order')
    raw_id_fields = ('match', 'match_replay')
    readonly_fields = ('match_replay', 'part_order')

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('match', 'match__team_home', 'match__team_guest', 'match_replay')
        )


@admin.register(MatchReplayStatsPlayer)
class MatchReplayStatsPlayerAdmin(UnfoldModelAdmin):
    list_display = (
        'match_id',
        'replay_stats',
        'team',
        'player',
        'nick',
        'avatar',
        'position',
        'played_ticks',
        'rating',
    )
    list_editable = ('position', 'played_ticks', 'rating')
    list_filter = (('team', RelatedDropdownFilter), ('replay_stats__match__id', SingleNumericFilter))
    search_fields = ('nick', 'player__nickname')
    ordering = ('-replay_stats__match_replay__id', 'replay_stats__part_order')
    raw_id_fields = ('replay_stats', 'player', 'team')
    list_filter_submit = True

    @display(description='ID матча')
    def match_id(self, model):
        return model.replay_stats.match_id

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('replay_stats__match', 'player', 'team')


class MatchIdFilter(SingleNumericFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = 'ID матча'


@admin.register(Goal)
class GoalAdmin(UnfoldModelAdmin):
    list_display = (
        'match',
        'kind',
        'team',
        'author',
        'assistent',
        'own_goal_team',
        'own_goal_author',
        'time_min',
        'time_sec',
    )
    ordering = ('-match_id', 'time_min', 'time_sec')
    raw_id_fields = ('match',)
    readonly_fields = ('legacy_event',)
    list_filter = (
        ('kind', MultipleChoicesDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
        ('assistent', RelatedDropdownFilter),
        ('own_goal_team', RelatedDropdownFilter),
        ('own_goal_author', RelatedDropdownFilter),
        ('match__id', MatchIdFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    conditional_fields = {
        'author': "kind == 'REG'",
        'assistent': "kind == 'REG'",
        'own_goal_team': "kind == 'OG'",
        'own_goal_author': "kind == 'OG'",
    }

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                'team',
                'author',
                'assistent',
                'own_goal_team',
                'own_goal_author',
                'match__team_home',
                'match__team_guest',
                'match__numb_tour',
            )
        )


@admin.register(Card)
class CardAdmin(UnfoldModelAdmin):
    list_display = ('id', 'kind', 'match', 'author', 'team', 'time_min', 'time_sec')
    ordering = ('-id',)
    raw_id_fields = ('match',)
    readonly_fields = ('legacy_event',)
    list_filter = (
        ('kind', MultipleChoicesDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
        ('match__league__championship', RelatedDropdownFilter),
        ('match__league', RelatedDropdownFilter),
        ('match__id', MatchIdFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('team', 'author', 'match__team_home', 'match__team_guest', 'match__numb_tour')
        )


@admin.register(CleanSheet)
class CleanSheetAdmin(UnfoldModelAdmin):
    list_display = ('id', 'period', 'match', 'author', 'team')
    ordering = ('-id',)
    raw_id_fields = ('match',)
    readonly_fields = ('legacy_event',)
    list_filter = (
        ('period', MultipleChoicesDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('author', RelatedDropdownFilter),
        ('match__league__championship', RelatedDropdownFilter),
        ('match__league', RelatedDropdownFilter),
        ('match__id', MatchIdFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('team', 'author', 'match__team_home', 'match__team_guest', 'match__numb_tour')
        )


@admin.register(Substitution)
class SubstitutionAdmin(UnfoldModelAdmin):
    list_display = ('match', 'team', 'player_out', 'player_in', 'time_min', 'time_sec')
    ordering = ('-id',)
    raw_id_fields = ('match',)
    list_filter = (
        ('team', RelatedDropdownFilter),
        ('player_out', RelatedDropdownFilter),
        ('player_in', RelatedDropdownFilter),
        ('match__id', MatchIdFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                'team', 'player_out', 'player_in', 'match__team_home', 'match__team_guest', 'match__numb_tour'
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
        ('match__league__championship', RelatedDropdownFilter),
        ('match__league', RelatedDropdownFilter),
        ('match__id', MatchIdFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    readonly_fields = ('match', 'team', 'author', 'time_min', 'time_sec', 'event', 'card_reason')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('team', 'author', 'match__team_home', 'match__team_guest', 'match__numb_tour')
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
            if 'object_id' not in resolved.kwargs:
                return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
                sort=db_field.sort,
                view_name=db_field.view_name,
            )
            kwargs['widget'] = widget

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_delete_permission(self, request, obj=None):
        return False


class MatchesTableSection(TableSection):
    related_name = 'tour_matches'
    fields = ['team_home', 'team_guest', 'display_result']

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
            super()
            .get_queryset(request)
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
    list_display = ('player', 'rating_points', 'grade', 'rating_update_status', 'version')
    list_filter = (
        ('version', RelatedDropdownFilter),
        ('player', RelatedDropdownFilter),
        ('player__team', RelatedDropdownFilter),
        ('grade', ChoicesCheckboxFilter),
        ('rating_update_status', ChoicesCheckboxFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False


@admin.register(TournamentWinner)
class TournamentWinnerAdmin(UnfoldModelAdmin):
    list_display = ('season', 'league', 'display_winner')
    list_filter = (
        ('season', RelatedDropdownFilter),
        ('league', RelatedDropdownFilter),
        ('winner', RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ('winner__title', 'league__title')
    ordering = ('-season__number', 'league__priority')

    @display(description='Победитель', header=True)
    def display_winner(self, model):
        return [
            model.winner.title,
            None,
            None,
            {
                'path': model.winner.logo.url,
                'squared': True,
                'borderless': True,
                'width': 24,
                'height': 24,
            },
        ]


@admin.register(AwardNomination)
class AwardNominationAdmin(UnfoldModelAdmin):
    list_display = ('name', 'code', 'order')
    list_editable = ('order',)
    ordering = ('order',)
    search_fields = ('name', 'code')


class AwardNomineeInline(UnfoldStackedInline):
    model = AwardNominee
    extra = 0
    tab = True
    fields = ('team', 'player')
    autocomplete_fields = ('player', 'team')


class AwardVoterInline(UnfoldStackedInline):
    model = AwardVoter
    extra = 0
    tab = True
    show_count = True
    fields = ('league', 'team', 'voter')
    autocomplete_fields = ('league', 'team', 'voter')


class AwardInline(UnfoldStackedInline):
    model = Award
    extra = 0
    tab = True
    show_count = True
    fields = ('league', 'nomination', 'max_nominees')
    autocomplete_fields = ('league', 'nomination')


class AwardVoteInline(UnfoldStackedInline):
    model = AwardVote
    extra = 0
    tab = True
    fields = ('award', 'nominee', 'place', 'points')
    autocomplete_fields = ('award', 'nominee')
    readonly_fields = ('points',)


@admin.register(AwardCampaign)
class AwardCampaignAdmin(UnfoldModelAdmin):
    list_display = ('season', 'voting_start_date', 'voting_end_date', 'results_public_date')
    list_filter = (('season', RelatedDropdownFilter),)
    list_filter_submit = True
    autocomplete_fields = ('season',)
    search_fields = ('season__title',)
    date_hierarchy = 'voting_start_date'
    ordering = ('-voting_start_date',)
    inlines = [AwardInline, AwardVoterInline]


@admin.register(Award)
class AwardAdmin(UnfoldModelAdmin):
    list_display = ('nomination', 'league', 'campaign')
    list_filter = (
        ('nomination', RelatedDropdownFilter),
        ('league', RelatedDropdownFilter),
        ('campaign', RelatedDropdownFilter),
    )
    list_filter_submit = True
    autocomplete_fields = ('campaign', 'league', 'nomination')
    search_fields = ('nomination__name', 'league__title', 'campaign__season__title')
    ordering = ('campaign__voting_start_date', 'nomination__order')
    inlines = [AwardNomineeInline]

    actions_detail = ['auto_populate_nominees']

    @action(description='Автозап. номинантов', variant=ActionVariant.PRIMARY)
    def auto_populate_nominees(self, request, object_id):
        award = Award.objects.get(id=object_id)
        if award.nomination.code == AwardNomination.Code.BEST_PLAYER:
            created = award.auto_populate_best_player_nominees()
            messages.success(request, f'Добавлено {created} номинантов для номинации "Игрок сезона".')
            return redirect(reverse_lazy('admin:tournament_award_change', args=[object_id]))
        if award.nomination.code == AwardNomination.Code.BEST_CAPTAIN:
            created = award.auto_populate_best_captain_nominees()
            messages.success(request, f'Добавлено {created} номинантов для номинации "Капитан сезона".')
            return redirect(reverse_lazy('admin:tournament_award_change', args=[object_id]))

        messages.error(request, 'Действие доступно только для номинаций "Игрок сезона" и "Капитан сезона".')
        return redirect(reverse_lazy('admin:tournament_award_change', args=[object_id]))


@admin.register(AwardNominee)
class AwardNomineeAdmin(UnfoldModelAdmin):
    list_display = ('award', 'team', 'player')
    list_filter = (
        ('award', RelatedDropdownFilter),
        ('team', RelatedDropdownFilter),
        ('player', AutocompleteSelectFilter),
    )
    list_filter_submit = True
    autocomplete_fields = ('award', 'player', 'team')
    search_fields = ('player__nickname', 'award__nomination__name', 'award__league__title', 'team__title')


@admin.register(AwardVoter)
class AwardVoterAdmin(UnfoldModelAdmin):
    list_display = ('id', 'campaign', 'league', 'team', 'voter')
    list_filter = (
        ('campaign', RelatedDropdownFilter),
        ('league', RelatedDropdownFilter),
        ('team', RelatedDropdownFilter),
    )
    list_filter_submit = True
    autocomplete_fields = ('campaign', 'league', 'team', 'voter')
    search_fields = ('team__title', 'voter__nickname', 'campaign__season__title', 'league__title')
    ordering = ('team__title', 'voter__nickname')


@admin.register(AwardSubmission)
class AwardSubmissionAdmin(UnfoldModelAdmin):
    list_display = ('id', 'voter_record', 'campaign', 'league', 'submitted_at')
    list_filter = (
        ('campaign', RelatedDropdownFilter),
        ('league', RelatedDropdownFilter),
        ('voter_record', RelatedDropdownFilter),
        ('voter_record__team', RelatedDropdownFilter),
    )
    list_filter_submit = True
    autocomplete_fields = ('voter_record', 'campaign', 'league')
    search_fields = (
        'voter_record__team__title',
        'campaign__season__title',
        'league__title',
        'voter_record__voter__nickname',
    )
    ordering = ('-submitted_at', 'voter_record__team__title', 'voter_record__voter__nickname')
    inlines = [AwardVoteInline]


@admin.register(AwardResult)
class AwardResultAdmin(UnfoldModelAdmin):
    list_display = (
        'award',
        'nominee',
        'total_points',
        'points_excluding_involved_teams',
        'first_place_votes',
        'second_place_votes',
        'third_place_votes',
        'final_rank',
        'last_calculated_at',
    )
    list_filter = (
        ('award', RelatedDropdownFilter),
        ('nominee', RelatedDropdownFilter),
    )
    list_filter_submit = True
    autocomplete_fields = ('award', 'nominee')
    search_fields = (
        'nominee__player__nickname',
        'nominee__team__title',
        'award__nomination__name',
        'award__league__title',
    )
    ordering = ('award', 'final_rank', '-total_points')
    readonly_fields = (
        'total_points',
        'points_excluding_involved_teams',
        'first_place_votes',
        'second_place_votes',
        'third_place_votes',
        'final_rank',
        'last_calculated_at',
    )
