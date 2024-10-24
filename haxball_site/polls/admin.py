from django.contrib import admin

# Register your models here.
from .models import Choice, Question


class ChoiceInline(admin.StackedInline):
    model = Choice
    filter_horizontal = ('votes',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'question_text', 'created', 'is_active', 'anonymously')
    list_display_links = ('title',)
    inlines = [ChoiceInline]
