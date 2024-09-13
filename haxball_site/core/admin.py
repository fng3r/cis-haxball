from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms
from django.contrib import admin
from django.contrib.admin import StackedInline
from django.urls import reverse
from django.utils.html import escape, mark_safe
from django_summernote.fields import SummernoteTextFormField

from .models import (
    Category,
    CommentHistoryItem,
    IPAdress,
    LikeDislike,
    NewComment,
    Post,
    Profile,
    Subscription,
    Themes,
    UserActivity,
    UserIcon,
    UserNicknameHistoryItem,
)

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
    list_display = (
        'id',
        'created',
        'version',
        'link_to_comment',
        'get_author',
        'body',
    )
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
    list_display = (
        'id',
        'author',
        'parent',
        'created',
        'edited',
        'body',
        'content_type',
        'object_id',
        'content_object',
    )
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
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    form = PostAdminForm
    list_editable = ('important',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'background', 'karma', 'views', 'can_comment')
    list_filter = ('id', 'name')
    list_display_links = ('name',)
    search_fields = ('name__username',)


@admin.register(Themes)
class ThemesAdmin(admin.ModelAdmin):
    list_display = ('title',)


@admin.register(UserIcon)
class UserIconAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'description',
    )
    filter_horizontal = ('user',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'description', 'is_official', 'theme')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(IPAdress)
class IPAdressAdmin(admin.ModelAdmin):
    list_display = ('ip', 'name', 'created', 'update', 'suspicious')
    list_filter = ('ip', 'name', 'suspicious')
    search_fields = ('ip', 'name__username')


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


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'starts_at', 'expires_at', 'tier', 'is_active', 'disabled')
    list_filter = ('user', 'tier', 'disabled')
    raw_id_fields = ('user',)
    search_fields = ('user__username',)

    def is_active(self, model):
        return model.is_active()

    is_active.boolean = True
    is_active.short_description = 'Активна'


@admin.register(UserNicknameHistoryItem)
class UserNicknameHistoryItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'nickname', 'edited')
    raw_id_fields = ('user',)
    search_fields = ('user__username', 'nickname')
