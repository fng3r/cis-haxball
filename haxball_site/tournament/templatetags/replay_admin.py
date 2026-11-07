from copy import copy

from django import template

register = template.Library()


@register.simple_tag
def replay_admin_groups(app_list):
    result = []
    for app in app_list:
        if app['app_label'] != 'tournament':
            result.append(app)
            continue
        buckets = [('Чемпионат', []), ('Реплеи и статистика', []), ('Реплеи — архивная статистика', [])]
        for model in app['models']:
            name = model['object_name']
            bucket = 1 if name.startswith('Replay') else 2 if name.startswith('MatchReplay') else 0
            buckets[bucket][1].append(model)
        for name, models in buckets:
            if models:
                group = copy(app)
                group.update(name=name, models=models)
                result.append(group)
    return result
