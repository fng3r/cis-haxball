from django.contrib import admin

from haxball_site.admin import UnfoldModelAdmin, UnfoldStackedInline

from .models import Choice, Question


class ChoiceInline(UnfoldStackedInline):
    model = Choice
    extra = 1
    filter_horizontal = ('votes',)


@admin.register(Question)
class QuestionAdmin(UnfoldModelAdmin):
    list_display = ('id', 'title', 'question_text', 'created', 'is_active', 'anonymously')
    list_display_links = ('title',)
    list_filter = ('is_active', 'anonymously')
    list_filter_sheet = False
    search_fields = ('title', 'question_text')
    search_help_text = 'Поиск по названию и тексту вопроса'
    inlines = [ChoiceInline]
