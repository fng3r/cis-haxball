from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django.contrib.admin import StackedInline
from django.utils.html import escape, mark_safe
from django_summernote.fields import SummernoteTextFormField
from django import forms
from django.contrib import admin

from .models import *


# Register your models here.


class PostAdminForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = Post
        fields = '__all__'


class CommentHistoryItemInline(StackedInline):
    model = CommentHistoryItem
    extra = 0
    verbose_name_plural = 'История изменения комментария'

    def has_add_permission(self, request, obj):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommentHistoryItem)
class CommentHistoryItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'created', 'version', 'link_to_comment', 'get_author', 'body',)
    list_filter = ('comment__author',)

    def get_author(self, model):
        return model.comment.author
    get_author.short_description = 'Автор'

    def link_to_comment(self, model):
        link = reverse('admin:core_newcomment_change', args=[model.comment.id])
        return mark_safe(f'<a href="{link}">{escape(model.comment.__str__())}</a>')
    link_to_comment.short_description = 'Базовый комментарий'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class NewCommentAdminForm(forms.ModelForm):
    body = SummernoteTextFormField(label='Комментарий')

    class Meta:
        model = NewComment
        fields = ('author', 'body', 'created', 'edited', 'content_type', 'object_id')


@admin.register(NewComment)
class NewCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'parent', 'created', 'edited', 'body', 'content_type', 'object_id', 'content_object')
    list_filter = ('created', 'author')
    search_fields = ('body',)
    inlines = [CommentHistoryItemInline]
    form = NewCommentAdminForm


@admin.register(LikeDislike)
class LikeDisLikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'vote', 'user', 'content_type', 'object_id', 'content_object')
    list_filter = ('user',)
    list_display_links = ('id',)
    list_editable = ('vote',)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'author', 'views', 'category', 'created', 'updated', 'important')
    list_filter = ('created', 'author')
    search_fields = ('title', 'body')
    # slug = AutoSlugField(populate_from='title', unique_for_date='publish')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    form = PostAdminForm
    list_editable = ('important',)

    # inlines = [CommentInline]


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'background', 'karma', 'views', 'can_comment')
    list_filter = ('id', 'name')
    list_display_links = ('name',)
    #readonly_fields = ('karma',)


@admin.register(Themes)
class ThemesAdmin(admin.ModelAdmin):
    list_display = ('title',)


@admin.register(UserIcon)
class UserIconAdmin(admin.ModelAdmin):
    list_display = ('title', 'description',)
    filter_horizontal = ('user',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'description', 'is_official', 'theme')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(IPAdress)
class IPAdressAdmin(admin.ModelAdmin):
    list_display = ('ip', 'name', 'created', 'update', 'suspicious')
    list_filter = ('ip', 'name')
    search_fields = ('ip',)


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip', 'id_token', 'user_agent', 'first_seen', 'last_seen', 'has_duplicates')
    list_filter = ('user', 'id_token', 'user_agent', 'has_duplicates')
    search_fields = ('user__username', 'ip', 'id_token')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
