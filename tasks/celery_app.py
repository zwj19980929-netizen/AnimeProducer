import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery import Celery
from config import settings

celery_app = Celery(
    "anime_producer",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.jobs", "tasks.shots"],
)

# Windows 兼容性：使用 solo 池代替 prefork（billiard 在 Windows 上有权限问题）
if sys.platform == "win32":
    celery_app.conf.worker_pool = "solo"

celery_app.conf.update(
    task_acks_late=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_annotations={
        "*": {
            "autoretry_for": (Exception,),
            "retry_backoff": True,
            "retry_backoff_max": 600,
            "retry_jitter": True,
            "max_retries": 3,
        }
    },
)
