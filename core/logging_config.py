"""Structured logging configuration for AnimeMatrix."""

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional

import structlog

from config import settings

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set request ID in context."""
    request_id_var.set(request_id)


def add_request_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Add request ID to log event."""
    request_id = get_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def add_timestamp(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """Add ISO timestamp to log event."""
    event_dict["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return event_dict


def configure_logging():
    """Configure structured logging for the application."""
    # Determine log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_timestamp,
            add_request_id,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if not settings.DEBUG else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Set log levels for noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def log_execution_time(logger: Optional[structlog.stdlib.BoundLogger] = None):
    """Decorator to log function execution time."""
    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = func.__name__

            logger.info(f"{func_name}_start", function=func_name)

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(
                    f"{func_name}_success",
                    function=func_name,
                    duration_ms=round(duration * 1000, 2)
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"{func_name}_failed",
                    function=func_name,
                    duration_ms=round(duration * 1000, 2),
                    error=str(e),
                    exc_info=True
                )
                raise

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = func.__name__

            logger.info(f"{func_name}_start", function=func_name)

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(
                    f"{func_name}_success",
                    function=func_name,
                    duration_ms=round(duration * 1000, 2)
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"{func_name}_failed",
                    function=func_name,
                    duration_ms=round(duration * 1000, 2),
                    error=str(e),
                    exc_info=True
                )
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class TaskLogger:
    """Logger wrapper for Celery tasks with execution tracking."""

    def __init__(self, task_name: str, task_id: str = None):
        self.logger = get_logger(task_name)
        self.task_name = task_name
        self.task_id = task_id or str(uuid.uuid4())
        self.start_time = None

    def start(self, **kwargs):
        """Log task start."""
        self.start_time = time.time()
        self.logger.info(
            "task_start",
            task_name=self.task_name,
            task_id=self.task_id,
            **kwargs
        )

    def progress(self, progress: float, **kwargs):
        """Log task progress."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        self.logger.info(
            "task_progress",
            task_name=self.task_name,
            task_id=self.task_id,
            progress=progress,
            elapsed_ms=round(elapsed * 1000, 2),
            **kwargs
        )

    def success(self, **kwargs):
        """Log task success."""
        duration = time.time() - self.start_time if self.start_time else 0
        self.logger.info(
            "task_success",
            task_name=self.task_name,
            task_id=self.task_id,
            duration_ms=round(duration * 1000, 2),
            **kwargs
        )

    def failure(self, error: Exception, **kwargs):
        """Log task failure."""
        duration = time.time() - self.start_time if self.start_time else 0
        self.logger.error(
            "task_failure",
            task_name=self.task_name,
            task_id=self.task_id,
            duration_ms=round(duration * 1000, 2),
            error=str(error),
            error_type=type(error).__name__,
            exc_info=True,
            **kwargs
        )

    def warning(self, message: str, **kwargs):
        """Log task warning."""
        self.logger.warning(
            message,
            task_name=self.task_name,
            task_id=self.task_id,
            **kwargs
        )

    def info(self, message: str, **kwargs):
        """Log task info."""
        self.logger.info(
            message,
            task_name=self.task_name,
            task_id=self.task_id,
            **kwargs
        )
