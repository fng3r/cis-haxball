from django.contrib import admin

from unfold.contrib.filters.admin import AutocompleteSelectFilter, RelatedDropdownFilter

from haxball_site.admin import UnfoldModelAdmin, UnfoldTabularInline

from .models import (
    LongTermPredictionItem,
    LongTermPredictionSubmission,
    Prediction,
    PredictionSubmission,
    PredictionTournament,
)


class PredictionInline(UnfoldTabularInline):
    model = Prediction
    extra = 0
    readonly_fields = ['match']
    fields = ['match', 'predicted_result', 'is_special']


@admin.register(PredictionTournament)
class PredictionTournamentAdmin(UnfoldModelAdmin):
    list_display = ['league', 'is_active']
    list_filter = ['is_active']
    search_fields = ['league__title']
    ordering = ['-id']


@admin.register(PredictionSubmission)
class PredictionSubmissionAdmin(UnfoldModelAdmin):
    list_filter = ['tournament', 'tour__league', 'created']
    search_fields = ['user__username', 'tour__number']
    ordering = ['-created']
    inlines = [PredictionInline]
    readonly_fields = ['user', 'tournament', 'tour', 'created', 'updated']


class LongTermPredictionItemInline(UnfoldTabularInline):
    model = LongTermPredictionItem
    extra = 0
    readonly_fields = ['team', 'position']
    fields = ['team', 'position']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LongTermPredictionSubmission)
class LongTermPredictionSubmissionAdmin(UnfoldModelAdmin):
    list_display = ['tournament', 'user', 'created', 'updated']
    list_filter = [('tournament__league', RelatedDropdownFilter), ('user', AutocompleteSelectFilter)]
    list_filter_submit = True
    search_fields = ['user__username', 'tournament__league__title']
    inlines = [LongTermPredictionItemInline]
