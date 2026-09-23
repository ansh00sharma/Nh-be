import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        if os.environ.get("OTEL_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
            return

        from core.observability.tracing import patch_drf_dispatch

        patch_drf_dispatch()
