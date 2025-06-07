from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from notifications.signals import notify


class Command(BaseCommand):
    help = 'Create a test notification for a user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username to create notification for')
        parser.add_argument('-c', '--count', type=int, default=3, help='Count of notifications to create')

    def handle(self, *args, **options):
        username = options['username']
        count = options['count']
        try:
            user = User.objects.get(username=username)

            # Create a test notification
            for i in range(count):
                notify.send(
                    sender=user,
                    recipient=user,
                    verb=f'This is a test notification {i}',
                    description='This is a test notification description',
                    data={'url': '/'},
                )

            self.stdout.write(self.style.SUCCESS(f'Successfully created {count} test notifications for {username}'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User {username} does not exist'))
