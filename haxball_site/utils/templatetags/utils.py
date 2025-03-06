from django import template

from haxball_site import settings

register = template.Library()

@register.simple_tag
def media(path):
    return f'{settings.MEDIA_URL}{path}'

@register.filter
def batch(iterable, batch_size):
    lst = list(iterable)
    return [lst[i:i + batch_size] for i in range(0, len(lst), batch_size)]
