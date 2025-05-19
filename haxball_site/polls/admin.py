from django.contrib import admin
from unfold import admin as unfold_admin

# Register your models here.
from .models import Choice, Question


class ChoiceInline(unfold_admin.StackedInline):
    model = Choice
    filter_horizontal = ('votes',)


@admin.register(Question)
class QuestionAdmin(unfold_admin.ModelAdmin):
    list_display = ('id', 'title', 'question_text', 'created', 'is_active', 'anonymously')
    list_display_links = ('title',)
    list_filter = ('is_active', 'anonymously')
    list_filter_sheet = False
    search_fields = ('title', 'question_text')
    search_help_text = 'Поиск по названию и тексту вопроса'
    inlines = [ChoiceInline]
