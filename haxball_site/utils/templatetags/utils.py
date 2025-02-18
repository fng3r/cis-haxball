from django import template

from haxball_site import settings

register = template.Library()

@register.simple_tag
def media(path):
    return f'{settings.MEDIA_URL}{path}'
