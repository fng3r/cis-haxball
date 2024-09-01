from django.core.management.base import BaseCommand

from ...models import Achievements


class Command(BaseCommand):
    help = 'Generate shedule'

    def handle(self, *args, **options):
        ach = Achievements.objects.all()
        for i in ach:
            i.position_number = i.id
            i.save()
