from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import UserNicknameHistoryItem


class Command(BaseCommand):
    help = 'Добавить прошлую историю никнеймов'

    def handle(self, *args, **options):
        with open('haxball_site/core/management/commands/nicknames.txt', 'r', encoding='utf-8') as file:
            lines = [line.strip() for line in file]
            i = 1
            errors = 0
            for line in lines:
                parts = line.split(': ')
                username = parts[0]
                nicknames = map(lambda x: x.strip(), parts[1].split('-->')[:-1])
                try:
                    user = User.objects.get(username=username)
                    nickname_index = 1
                    for nickname in nicknames:
                        UserNicknameHistoryItem.objects.create(
                            user=user, nickname=nickname, edited=timezone.datetime(2024, 1, 1, nickname_index)
                        )
                        nickname_index += 1
                        print('{}. {}: {}'.format(i, username, nickname), ' SUCCESS')
                except Exception as e:
                    errors += 1
                    print('{}. {}: {}'.format(i, username, nickname), ' FAIL')
                    print('ERROR: ', e)
                    # print('{}. {}'.format(errors, username))
                i += 1
