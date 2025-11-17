from django.apps import AppConfig


class TournamentConfig(AppConfig):
    name = 'tournament'
    verbose_name = '3. Чемпионат'

    def ready(self):
        import tournament.signals  # noqa: F401
