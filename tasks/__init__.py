"""Lazy task package exports.

The API process imports ``tasks.celery_app`` to cancel/query jobs, but it does
not need to eagerly import every task module. Some task modules instantiate the
full AI pipeline at import time, which makes the web app startup depend on
optional heavyweight provider SDKs being installed. We keep package-level
exports for compatibility, but resolve them lazily on first access instead.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "celery_app",
    "render_project_job",
    "compose_project",
    "render_shot",
    "render_shot_seedance",
    "generate_character_images_task",
    "generate_character_variants_task",
    "batch_generate_character_variants_task",
    "start_lora_training_task",
]

_EXPORT_MAP = {
    "celery_app": ("tasks.celery_app", "celery_app"),
    "render_project_job": ("tasks.jobs", "render_project_job"),
    "compose_project": ("tasks.jobs", "compose_project"),
    "render_shot": ("tasks.shots", "render_shot"),
    "render_shot_seedance": ("tasks.shots", "render_shot_seedance"),
    "generate_character_images_task": ("tasks.assets", "generate_character_images_task"),
    "generate_character_variants_task": ("tasks.assets", "generate_character_variants_task"),
    "batch_generate_character_variants_task": ("tasks.assets", "batch_generate_character_variants_task"),
    "start_lora_training_task": ("tasks.assets", "start_lora_training_task"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module 'tasks' has no attribute {name!r}")

    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
