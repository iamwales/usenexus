from __future__ import annotations

from celery import Celery
from nexus_core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "nexus_worker",
    broker=getattr(settings, "celery_broker_url", None) or "redis://localhost:6379/1",
    backend=getattr(settings, "celery_result_backend", None) or "redis://localhost:6379/2",
    include=[
        "nexus_worker.tasks.full_sync",
        "nexus_worker.tasks.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
