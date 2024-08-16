from django import forms
from django.contrib import admin
from django.db.models import Q
from django.urls import resolve

from .models import FreeAgent, Player, League, Team, Match, Goal, OtherEvents, Substitution, Season, PlayerTransfer, \
    TourNumber, Nation, Achievements, TeamAchievement, AchievementCategory, Disqualification, Postponement, \
    PostponementSlots, SeasonTeamRating, RatingVersion, TeamRating


@admin.register(FreeAgent)
class FreeAgentAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'position_main', 'description', 'is_active', 'created', 'deleted')


@admin.register(AchievementCategory)
class AchievmentCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'description', 'order')


@admin.register(Achievements)
class AchievementsAdmin(admin.ModelAdmin):
    list_display = ('id', 'position_number', 'title', 'description', 'category', 'image', 'mini_image')
    filter_horizontal = ('player',)
    search_fields = ('title__icontains', 'description__icontains',)


@admin.register(TeamAchievement)
class TeamAchievementAdmin(admin.ModelAdmin):
    list_display = ('id', 'season', 'title', 'description', 'players_raw_list', 'position_number', 'image')
    filter_horizontal = ('team',)
    search_fields = ('title__icontains', 'description__icontains',)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'nickname', 'team', 'player_nation', 'role',)
    raw_id_fields = ('name',)
    list_filter = ('role', 'team', 'name')
    search_fields = ('nickname', 'name__username',)


@admin.register(PlayerTransfer)
class PlayerTransferAdmin(admin.ModelAdmin):
    list_display = ('trans_player', 'from_team', 'to_team', 'date_join', 'season_join')
    list_filter = ('trans_player', 'from_team', 'to_team',)
    search_fields = ('trans_player__nickname', 'from_team__title', 'to_team__title',)
    # autocomplete_fields = ('trans_player',)
    raw_id_fields = ('trans_player',)
    ordering = ('-date_join', '-id',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'from_team' or db_field.name == 'to_team':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class PlayerInline(admin.StackedInline):
    model = Player

    def has_add_permission(self, request, obj):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('title', 'short_title', 'owner',)
    search_fields = ('title',)
    inlines = [PlayerInline]


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'is_active', 'created')


@admin.register(Nation)
class NationAdmin(admin.ModelAdmin):
    list_display = ('country',)


@admin.register(Disqualification)
class DisqualificationAdmin(admin.ModelAdmin):
    list_display = ('match', 'team', 'player', 'reason', 'get_tours', 'get_lifted_tours', 'created')
    filter_horizontal = ('tours', 'lifted_tours')

    def get_tours(self, model):
        return ', '.join(map(lambda t: str(t), model.tours.all()))
    get_tours.short_description = 'Туры'

    def get_lifted_tours(self, model):
        return ', '.join(map(lambda t: str(t), model.lifted_tours.all()))
    get_lifted_tours.short_description = 'Отмененные туры'

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'tours' or db_field.name == 'lifted_tours':
            kwargs['queryset'] = TourNumber.objects.filter(league__championship__is_active=True).order_by('number')
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class AlwaysChangedModelForm(forms.ModelForm):
    def has_changed(self):
        """ Should returns True if data differs from initial.
        By always returning true even unchanged inlines will get validated and saved."""
        return True


class PostponementSlotsInline(admin.TabularInline):
    model = PostponementSlots
    form = AlwaysChangedModelForm
    min_num = 1
    max_num = 1

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Postponement)
class PostponementAdmin(admin.ModelAdmin):
    list_display = ('match', 'is_emergency', 'get_teams', 'starts_at', 'ends_at', 'taken_at', 'taken_by',
                    'is_cancelled', 'cancelled_at', 'cancelled_by')
    filter_horizontal = ('teams',)
    raw_id_fields = ('match', 'taken_by', 'cancelled_by')
    # autocomplete_fields = ('taken_by', 'cancelled_by')
    list_filter = ('match__league', 'is_emergency')
    search_fields = ('match__team_home__title', 'match__team_guest__title')

    def get_teams(self, model):
        return ', '.join(map(lambda t: str(t), model.teams.all()))
    get_teams.short_description = 'На кого взят перенос'

    def is_cancelled(self, model):
        return model.is_cancelled
    is_cancelled.short_description = 'Отменен'
    is_cancelled.boolean = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'match':
            kwargs['queryset'] = Match.objects.filter(league__championship__is_active=True).order_by('numb_tour__number')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == 'teams':
            kwargs['queryset'] = Team.objects.filter(leagues__championship__is_active=True).distinct()
        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_cup', 'priority', 'championship', 'created')
    filter_horizontal = ('teams',)
    inlines = [PostponementSlotsInline]


class GoalInline(admin.StackedInline):
    model = Goal
    extra = 3

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        not_found = False
        try:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == "team" and not not_found:
            kwargs["queryset"] = Team.objects.filter(Q(home_matches=match) | Q(guest_matches=match)).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SubstitutionInline(admin.StackedInline):
    model = Substitution
    extra = 3

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        not_found = False
        try:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == "team" and not not_found:
            kwargs["queryset"] = Team.objects.filter(Q(home_matches=match) | Q(guest_matches=match)).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class DisqualificationInline(admin.StackedInline):
    model = Disqualification
    extra = 1
    filter_horizontal = ('tours',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "team":
            kwargs["queryset"] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tours":
            kwargs["queryset"] = TourNumber.objects.filter(league__championship__is_active=True).order_by('number')
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class EventInline(admin.StackedInline):
    model = OtherEvents
    extra = 2

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        not_found = False
        try:
            match = self.parent_model.objects.get(id=resolved.kwargs['object_id'])
        except:
            not_found = True
        if db_field.name == "team" and not not_found:
            kwargs["queryset"] = Team.objects.filter(leagues__championship__is_active=True).distinct().order_by('title')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'league', 'numb_tour', 'team_home', 'score_home', 'team_guest', 'score_guest', 'is_played', 'updated',
        'inspector', 'id',)
    search_fields = ('team_home__title', 'team_guest__title')
    filter_horizontal = ('team_home_start', 'team_guest_start',)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Берём из пути id матча
        resolved = resolve(request.path_info)
        
        if db_field.name == 'team_home_start':
            # Игроки команды хозяев
            t = Team.objects.filter(home_matches=resolved.kwargs.get("object_id")).first()
            kwargs["queryset"] = Player.objects.filter(team=t)
        if db_field.name == 'team_guest_start':
            # Игроки команды гостей
            t = Team.objects.filter(guest_matches=resolved.kwargs.get("object_id")).first()
            kwargs["queryset"] = Player.objects.filter(team=t)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    list_filter = ('numb_tour__number', 'league', 'inspector', 'is_played')
    fieldsets = (
        ('Основная инфа', {
            'fields': (('league', 'is_played', 'match_date', 'numb_tour',),)
        }),
        (None, {
            'fields': (('team_home', 'team_guest', 'replay_link',),)
        }),
        (None, {
            'fields': (('score_home', 'score_guest', 'inspector', 'replay_link_second'),)
        }),
        ('Составы', {
            'classes': ('grp-collapse grp-closed',),
            'fields': ('team_home_start', 'team_guest_start',)
        }),
        ('Комментарий:', {
            'classes': ('grp-collapse grp-closed',),
            'fields': ('comment',)
        })
    )
    inlines = [GoalInline, SubstitutionInline, EventInline, DisqualificationInline]


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('match', 'author', 'assistent', 'id')


@admin.register(Substitution)
class SubstitutionAdmin(admin.ModelAdmin):
    list_display = ('match', 'player_out', 'player_in')


@admin.register(OtherEvents)
class OtherEventsAdmin(admin.ModelAdmin):
    list_display = ('event', 'match', 'author',)


@admin.register(TourNumber)
class MatchTourAdmin(admin.ModelAdmin):
    list_display = ('number', 'league', 'date_from', 'date_to', 'is_actual')
    list_filter = ('league', 'number')

    def is_actual(self, model):
        return model.is_actual
    is_actual.short_description = 'Актуальный'
    is_actual.boolean = True


@admin.register(SeasonTeamRating)
class SeasonTeamRatingAdmin(admin.ModelAdmin):
    list_display = ('season', 'team', 'points_for_matches')
    list_filter = ('season', 'team')


@admin.register(RatingVersion)
class RatingVersionAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'related_season')


@admin.register(TeamRating)
class TeamRatingAdmin(admin.ModelAdmin):
    list_display = ('version', 'rank', 'team', 'total_points')
    list_filter = ('version', 'team')
