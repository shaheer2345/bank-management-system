from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = 'audit'

    def ready(self):
        # import signal handlers so they are registered
        from . import signals  # noqa

