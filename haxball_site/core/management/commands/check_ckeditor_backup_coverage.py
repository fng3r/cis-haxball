from django.core.management.base import BaseCommand

from core.models import NewComment, Post


class Command(BaseCommand):
    help = 'Check coverage of CKEditor4 backup fields for posts and comments.'

    def handle(self, *args, **options):
        stats = [
            ('Post', Post.objects.exclude(body='')),
            ('NewComment', NewComment.objects.exclude(body='')),
        ]

        for model_name, queryset in stats:
            total = queryset.count()
            backed_up = queryset.exclude(body_ck4_backup__isnull=True).count()
            missing = total - backed_up
            percent = 0 if total == 0 else (backed_up / total) * 100
            self.stdout.write(
                f'[{model_name}] total={total}, backed_up={backed_up}, missing={missing}, coverage={percent:.2f}%'
            )
