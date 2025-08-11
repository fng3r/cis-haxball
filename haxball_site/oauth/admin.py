from django.contrib import admin

from oauth2_provider.admin import AccessTokenAdmin as BaseAccessTokenAdmin
from oauth2_provider.admin import ApplicationAdmin as BaseApplicationAdmin
from oauth2_provider.admin import GrantAdmin as BaseGrantAdmin
from oauth2_provider.admin import RefreshTokenAdmin as BaseRefreshTokenAdmin
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken
from unfold.admin import ModelAdmin as UnfoldModelAdmin

# Unregister default OAuth2 provider admin models
admin.site.unregister(Application)
admin.site.unregister(AccessToken)
admin.site.unregister(RefreshToken)
admin.site.unregister(Grant)


@admin.register(Application)
class ApplicationAdmin(BaseApplicationAdmin, UnfoldModelAdmin):
    list_display = ('name', 'client_type', 'authorization_grant_type', 'created', 'updated')
    list_filter = ('client_type', 'authorization_grant_type', 'created')
    list_filter_sheet = True
    search_fields = ('name', 'client_id')
    search_help_text = 'Поиск по названию или Client ID'
    readonly_fields = ('client_id', 'client_secret', 'created', 'updated')


@admin.register(AccessToken)
class AccessTokenAdmin(BaseAccessTokenAdmin, UnfoldModelAdmin):
    list_display = ('token', 'user', 'application', 'scope', 'expires', 'created')
    list_filter = ('application', 'scope', 'expires', 'created')
    list_filter_sheet = True
    search_fields = ('user__username', 'application__name', 'token')
    search_help_text = 'Поиск по пользователю, приложению или токену'
    readonly_fields = ('token', 'created', 'updated')


@admin.register(RefreshToken)
class RefreshTokenAdmin(BaseRefreshTokenAdmin, UnfoldModelAdmin):
    list_display = ('token', 'user', 'application', 'created')
    list_filter = ('application', 'created')
    list_filter_sheet = True
    search_fields = ('user__username', 'application__name', 'token')
    search_help_text = 'Поиск по пользователю, приложению или токену'
    readonly_fields = ('token', 'created', 'updated')


@admin.register(Grant)
class GrantAdmin(BaseGrantAdmin, UnfoldModelAdmin):
    list_display = ('code', 'user', 'application', 'expires', 'created')
    list_filter = ('application', 'expires', 'created')
    list_filter_sheet = True
    search_fields = ('user__username', 'application__name', 'code')
    search_help_text = 'Поиск по пользователю, приложению или коду'
    readonly_fields = ('code', 'created', 'updated')
