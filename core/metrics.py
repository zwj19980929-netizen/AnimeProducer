"""Prometheus metrics for monitoring AnimeMatrix."""

import time
import logging
from functools import wraps
from typing import Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

# Try to import prometheus_client, gracefully handle if not installed
try:
    from prometheus_client import Counter, Histogram, Gauge, Info, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics will be disabled")


if PROMETHEUS_AVAILABLE:
    # ==================== Application Info ====================
    app_info = Info("animematrix_app", "Application information")
    app_info.info({
        "version": settings.API_VERSION,
        "name": settings.PROJECT_NAME
    })

    # ==================== HTTP Metrics ====================
    http_requests_total = Counter(
        "animematrix_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"]
    )

    http_request_duration_seconds = Histogram(
        "animematrix_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    )

    http_requests_in_progress = Gauge(
        "animematrix_http_requests_in_progress",
        "Number of HTTP requests in progress",
        ["method", "endpoint"]
    )

    # ==================== Job Metrics ====================
    jobs_total = Counter(
        "animematrix_jobs_total",
        "Total jobs processed",
        ["job_type", "status"]
    )

    jobs_duration_seconds = Histogram(
        "animematrix_jobs_duration_seconds",
        "Job duration in seconds",
        ["job_type"],
        buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0)
    )

    jobs_in_progress = Gauge(
        "animematrix_jobs_in_progress",
        "Number of jobs currently in progress",
        ["job_type"]
    )

    # ==================== Shot Render Metrics ====================
    shot_renders_total = Counter(
        "animematrix_shot_renders_total",
        "Total shot renders",
        ["status"]
    )

    shot_render_duration_seconds = Histogram(
        "animematrix_shot_render_duration_seconds",
        "Shot render duration in seconds",
        ["stage"],
        buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
    )

    # ==================== External API Metrics ====================
    external_api_requests_total = Counter(
        "animematrix_external_api_requests_total",
        "Total external API requests",
        ["service", "status"]
    )

    external_api_duration_seconds = Histogram(
        "animematrix_external_api_duration_seconds",
        "External API request duration in seconds",
        ["service"],
        buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
    )

    external_api_errors_total = Counter(
        "animematrix_external_api_errors_total",
        "Total external API errors",
        ["service", "error_type"]
    )

    # ==================== Database Metrics ====================
    db_queries_total = Counter(
        "animematrix_db_queries_total",
        "Total database queries",
        ["operation"]
    )

    db_query_duration_seconds = Histogram(
        "animematrix_db_query_duration_seconds",
        "Database query duration in seconds",
        ["operation"],
        buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
    )

    # ==================== Cache Metrics ====================
    cache_hits_total = Counter(
        "animematrix_cache_hits_total",
        "Total cache hits",
        ["cache_type"]
    )

    cache_misses_total = Counter(
        "animematrix_cache_misses_total",
        "Total cache misses",
        ["cache_type"]
    )

    # ==================== WebSocket Metrics ====================
    websocket_connections = Gauge(
        "animematrix_websocket_connections",
        "Number of active WebSocket connections",
        ["type"]
    )

    websocket_messages_total = Counter(
        "animematrix_websocket_messages_total",
        "Total WebSocket messages",
        ["direction", "type"]
    )


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not installed\n"
    return generate_latest()


def get_metrics_content_type() -> str:
    """Get content type for metrics endpoint."""
    if not PROMETHEUS_AVAILABLE:
        return "text/plain"
    return CONTENT_TYPE_LATEST


# ==================== Metric Decorators ====================

def track_http_request(method: str, endpoint: str):
    """Decorator to track HTTP request metrics."""
    def decorator(func: Callable) -> Callable:
        if not PROMETHEUS_AVAILABLE:
            return func

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
            start_time = time.time()
            status_code = "500"
            try:
                response = await func(*args, **kwargs)
                status_code = str(getattr(response, "status_code", 200))
                return response
            except Exception as e:
                status_code = "500"
                raise
            finally:
                duration = time.time() - start_time
                http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
                http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
                http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
            start_time = time.time()
            status_code = "500"
            try:
                response = func(*args, **kwargs)
                status_code = str(getattr(response, "status_code", 200))
                return response
            except Exception as e:
                status_code = "500"
                raise
            finally:
                duration = time.time() - start_time
                http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
                http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
                http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_job(job_type: str):
    """Decorator to track job metrics."""
    def decorator(func: Callable) -> Callable:
        if not PROMETHEUS_AVAILABLE:
            return func

        @wraps(func)
        def wrapper(*args, **kwargs):
            jobs_in_progress.labels(job_type=job_type).inc()
            start_time = time.time()
            status = "failure"
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception:
                status = "failure"
                raise
            finally:
                duration = time.time() - start_time
                jobs_total.labels(job_type=job_type, status=status).inc()
                jobs_duration_seconds.labels(job_type=job_type).observe(duration)
                jobs_in_progress.labels(job_type=job_type).dec()

        return wrapper

    return decorator


def track_external_api(service: str):
    """Decorator to track external API call metrics."""
    def decorator(func: Callable) -> Callable:
        if not PROMETHEUS_AVAILABLE:
            return func

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "error"
            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                external_api_errors_total.labels(service=service, error_type=type(e).__name__).inc()
                raise
            finally:
                duration = time.time() - start_time
                external_api_requests_total.labels(service=service, status=status).inc()
                external_api_duration_seconds.labels(service=service).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            status = "error"
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception as e:
                status = "error"
                external_api_errors_total.labels(service=service, error_type=type(e).__name__).inc()
                raise
            finally:
                duration = time.time() - start_time
                external_api_requests_total.labels(service=service, status=status).inc()
                external_api_duration_seconds.labels(service=service).observe(duration)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ==================== Manual Metric Recording ====================

def record_job_start(job_type: str):
    """Record job start."""
    if PROMETHEUS_AVAILABLE:
        jobs_in_progress.labels(job_type=job_type).inc()


def record_job_end(job_type: str, status: str, duration: float):
    """Record job completion."""
    if PROMETHEUS_AVAILABLE:
        jobs_total.labels(job_type=job_type, status=status).inc()
        jobs_duration_seconds.labels(job_type=job_type).observe(duration)
        jobs_in_progress.labels(job_type=job_type).dec()


def record_shot_render(status: str, stage: str, duration: float):
    """Record shot render metrics."""
    if PROMETHEUS_AVAILABLE:
        shot_renders_total.labels(status=status).inc()
        shot_render_duration_seconds.labels(stage=stage).observe(duration)


def record_cache_hit(cache_type: str):
    """Record cache hit."""
    if PROMETHEUS_AVAILABLE:
        cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str):
    """Record cache miss."""
    if PROMETHEUS_AVAILABLE:
        cache_misses_total.labels(cache_type=cache_type).inc()


def record_websocket_connect(ws_type: str):
    """Record WebSocket connection."""
    if PROMETHEUS_AVAILABLE:
        websocket_connections.labels(type=ws_type).inc()


def record_websocket_disconnect(ws_type: str):
    """Record WebSocket disconnection."""
    if PROMETHEUS_AVAILABLE:
        websocket_connections.labels(type=ws_type).dec()


def record_websocket_message(direction: str, msg_type: str):
    """Record WebSocket message."""
    if PROMETHEUS_AVAILABLE:
        websocket_messages_total.labels(direction=direction, type=msg_type).inc()
