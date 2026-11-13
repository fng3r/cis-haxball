"""Build the test schema directly: this repository does not track app migrations."""

from .settings import *  # noqa: F403
from .settings import DATABASES


class DisableMigrations(dict):
    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        return None


MIGRATION_MODULES = DisableMigrations()
# Keep this suite separate from other checkouts' default test_hax_db database.
DATABASES['default'].setdefault('TEST', {})['NAME'] = 'test_cis_haxball'
