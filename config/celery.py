import os

from celery import Celery
from celery.signals import worker_init, worker_process_init


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("taskflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_init.connect(weak=False)
@worker_process_init.connect(weak=False)
def initialize_celery_tracing(**kwargs):
    from core.observability import initialize_tracing

    initialize_tracing()
