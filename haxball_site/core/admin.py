from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils.html import escape, mark_safe

from unfold import admin as unfold_admin
from unfold.contrib.filters.admin import (
    FieldTextFilter,
    SingleNumericFilter,
    RelatedDropdownFilter,
    ChoicesCheckboxFilter
)
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from online_users.models import OnlineUserActivity

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
admin.site.unregister(User)
admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin, unfold_admin.ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    
    list_display = ('username', 'email', 'is_active', 'is_staff', 'is_superuser')
    list_filter_sheet = True


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, unfold_admin.ModelAdmin):
    pass

    
admin.site.unregister(OnlineUserActivity)

@admin.register(OnlineUserActivity)
class OnlineUserActivityAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'last_activity')
    list_filter = ('last_activity',)
    list_filter_sheet = False
    search_fields = ('user__username',)
    search_help_text = 'Поиск по пользователям'
    ordering = ('-last_activity',)


class PostAdminForm(forms.ModelForm):
    body = forms.CharField(label='Пост', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = Post
        fields = '__all__'


class CommentHistoryItemInline(unfold_admin.StackedInline):
    model = CommentHistoryItem
    verbose_name_plural = 'История изменения комментария'

    def has_add_permission(self, request, obj):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommentHistoryItem)
class CommentHistoryItemAdmin(unfold_admin.ModelAdmin):
    list_display = (
        'id',
        'created',
        'version',
        'link_to_comment',
        'get_author',
        'body',
    )
    list_filter = (('comment__author', RelatedDropdownFilter),)
    list_filter_submit = True
    search_fields = ('body',)
    search_help_text = 'Поиск по тексту комментария'

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
    body = forms.CharField(label='Комментарий', widget=CKEditorUploadingWidget(config_name='default'))

    class Meta:
        model = NewComment
        fields = ('author', 'body', 'created', 'edited', 'content_type', 'object_id')


@admin.register(NewComment)
class NewCommentAdmin(unfold_admin.ModelAdmin):
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
    list_filter = ('created', ('author', RelatedDropdownFilter))
    list_filter_submit = True
    list_fullwidth = True
    search_fields = ('author__username', 'body',)
    search_help_text = 'Поиск по автору/тексту комментария'
    inlines = [CommentHistoryItemInline]
    form = NewCommentAdminForm


@admin.register(LikeDislike)
class LikeDisLikeAdmin(unfold_admin.ModelAdmin):
    list_display = ('id', 'vote', 'user', 'content_type', 'object_id', 'content_object')
    list_filter = ('vote', ('user', RelatedDropdownFilter),)
    list_filter_submit = True
    list_filter_sheet = False
    list_display_links = ('id',)


@admin.register(Post)
class PostAdmin(unfold_admin.ModelAdmin):
    list_display = ('id', 'title', 'author', 'views', 'category', 'created', 'updated', 'important')
    list_filter = ('created', ('author', RelatedDropdownFilter), 'important')
    list_filter_submit = True
    search_fields = ('title', 'body')
    search_help_text = 'Поиск по автору/заголовку поста'
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    form = PostAdminForm
    list_editable = ('important',)


@admin.register(Profile)
class ProfileAdmin(unfold_admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'can_comment', 'can_vote', 'views', 'karma', 'background')
    list_filter = (
        ('id', SingleNumericFilter),
        ('name', RelatedDropdownFilter),
        'can_comment',
        'can_vote'
    )
    list_filter_submit = True
    search_fields = ('name__username',)
    search_help_text = 'Поиск по имени пользователя'
    list_editable = ('can_comment', 'can_vote')


@admin.register(Themes)
class ThemesAdmin(unfold_admin.ModelAdmin):
    list_display = ('title',)


@admin.register(UserIcon)
class UserIconAdmin(unfold_admin.ModelAdmin):
    list_display = ('title', 'description', 'priority')
    list_filter = (('user', RelatedDropdownFilter),)
    list_filter_submit = True
    list_filter_sheet = False
    show_facets = False
    filter_horizontal = ('user',)


@admin.register(Category)
class CategoryAdmin(unfold_admin.ModelAdmin):
    list_display = ('title', 'slug', 'description', 'is_official', 'theme')
    list_filter = ('is_official', 'theme')
    list_filter_sheet = False
    prepopulated_fields = {'slug': ('title',)}


@admin.register(IPAdress)
class IPAdressAdmin(unfold_admin.ModelAdmin):
    list_display = ('ip', 'name', 'created', 'update', 'suspicious')
    list_filter = (('name', RelatedDropdownFilter), 'suspicious', 'created', 'update')
    list_filter_submit = True
    search_fields = ('ip', 'name__username')
    search_help_text = 'Поиск по имени пользователя/ip-адресу'


@admin.register(UserActivity)
class UserActivityAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'ip', 'id_token', 'user_agent', 'first_seen', 'last_seen', 'has_duplicates')
    list_filter = (('user', RelatedDropdownFilter), ('user_agent', FieldTextFilter), 'has_duplicates')
    list_filter_submit = True
    search_fields = ('user__username', 'ip', 'id_token')
    search_help_text = 'Поиск по имени пользователя/ip/id token'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Subscription)
class SubscriptionAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'starts_at', 'expires_at', 'tier', 'is_active', 'disabled')
    list_filter = (('user', RelatedDropdownFilter), ('tier', ChoicesCheckboxFilter), 'disabled')
    list_filter_submit = True
    raw_id_fields = ('user',)
    search_fields = ('user__username',)
    search_help_text = 'Поиск по имени пользователя'

    def is_active(self, model):
        return model.is_active()

    is_active.boolean = True
    is_active.short_description = 'Активна'


@admin.register(UserNicknameHistoryItem)
class UserNicknameHistoryItemAdmin(unfold_admin.ModelAdmin):
    list_display = ('user', 'nickname', 'edited')
    raw_id_fields = ('user',)
    search_fields = ('user__username', 'nickname')
