from django import template
from django.utils.timesince import timesince

from haxball_site import settings

register = template.Library()


@register.simple_tag
def media(path):
    return f'{settings.MEDIA_URL}{path}'


@register.filter
def batch(iterable, batch_size):
    lst = list(iterable)
    return [lst[i : (i + batch_size)] for i in range(0, len(lst), batch_size)]


@register.filter
def get(d: dict, key):
    return d[key]


@register.filter
def get_or_default(d: dict, key, default=None):
    return d.get(key, default)


@register.filter
def contains(collection, item):
    return item in collection


@register.filter(name='nbsp2space', is_safe=True)
def nbsp2space(value: str) -> str:
    return value.replace('&nbsp;', ' ')


@register.filter
def timesince_single_unit(value):
    if not value:
        return ''
    result = timesince(value)

    return result.split(',')[0]
