"""Redis cache service for job status and other frequently accessed data."""

import json
import logging
from typing import Optional, Any
from datetime import timedelta

import redis

from config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis cache service for caching job status and other data."""

    _instance: Optional["RedisCache"] = None

    def __init__(self):
        self._client: Optional[redis.Redis] = None
        self._connected = False

    @classmethod
    def get_instance(cls) -> "RedisCache":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            try:
                self._client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                self._client.ping()
                self._connected = True
                logger.info("Redis cache connected")
            except redis.ConnectionError as e:
                logger.warning(f"Redis connection failed: {e}")
                self._connected = False
                raise
        return self._client

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        if not self._connected:
            return False
        try:
            self._get_client().ping()
            return True
        except Exception:
            self._connected = False
            return False

    # ==================== Job Status Cache ====================

    def get_job_status(self, job_id: str) -> Optional[str]:
        """Get cached job status."""
        try:
            return self._get_client().get(f"job:{job_id}:status")
        except Exception as e:
            logger.warning(f"Failed to get job status from cache: {e}")
            return None

    def set_job_status(self, job_id: str, status: str, ttl: int = 3600) -> bool:
        """Cache job status with TTL."""
        try:
            self._get_client().setex(f"job:{job_id}:status", ttl, status)
            return True
        except Exception as e:
            logger.warning(f"Failed to set job status in cache: {e}")
            return False

    def get_job_progress(self, job_id: str) -> Optional[float]:
        """Get cached job progress."""
        try:
            value = self._get_client().get(f"job:{job_id}:progress")
            return float(value) if value else None
        except Exception as e:
            logger.warning(f"Failed to get job progress from cache: {e}")
            return None

    def set_job_progress(self, job_id: str, progress: float, ttl: int = 3600) -> bool:
        """Cache job progress with TTL."""
        try:
            self._get_client().setex(f"job:{job_id}:progress", ttl, str(progress))
            return True
        except Exception as e:
            logger.warning(f"Failed to set job progress in cache: {e}")
            return False

    def get_job_data(self, job_id: str) -> Optional[dict]:
        """Get full cached job data."""
        try:
            data = self._get_client().get(f"job:{job_id}:data")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning(f"Failed to get job data from cache: {e}")
            return None

    def set_job_data(self, job_id: str, data: dict, ttl: int = 3600) -> bool:
        """Cache full job data with TTL."""
        try:
            self._get_client().setex(f"job:{job_id}:data", ttl, json.dumps(data))
            return True
        except Exception as e:
            logger.warning(f"Failed to set job data in cache: {e}")
            return False

    def invalidate_job(self, job_id: str) -> bool:
        """Invalidate all cached data for a job."""
        try:
            client = self._get_client()
            client.delete(
                f"job:{job_id}:status",
                f"job:{job_id}:progress",
                f"job:{job_id}:data"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to invalidate job cache: {e}")
            return False

    # ==================== Project Cache ====================

    def get_project_status(self, project_id: str) -> Optional[str]:
        """Get cached project status."""
        try:
            return self._get_client().get(f"project:{project_id}:status")
        except Exception as e:
            logger.warning(f"Failed to get project status from cache: {e}")
            return None

    def set_project_status(self, project_id: str, status: str, ttl: int = 3600) -> bool:
        """Cache project status with TTL."""
        try:
            self._get_client().setex(f"project:{project_id}:status", ttl, status)
            return True
        except Exception as e:
            logger.warning(f"Failed to set project status in cache: {e}")
            return False

    def invalidate_project(self, project_id: str) -> bool:
        """Invalidate all cached data for a project."""
        try:
            client = self._get_client()
            # Delete project-related keys
            keys = client.keys(f"project:{project_id}:*")
            if keys:
                client.delete(*keys)
            return True
        except Exception as e:
            logger.warning(f"Failed to invalidate project cache: {e}")
            return False

    # ==================== Generic Cache Operations ====================

    def get(self, key: str) -> Optional[str]:
        """Get a value from cache."""
        try:
            return self._get_client().get(key)
        except Exception as e:
            logger.warning(f"Failed to get from cache: {e}")
            return None

    def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """Set a value in cache with TTL."""
        try:
            self._get_client().setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Failed to set in cache: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            self._get_client().delete(key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete from cache: {e}")
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """Get a JSON value from cache."""
        try:
            data = self._get_client().get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning(f"Failed to get JSON from cache: {e}")
            return None

    def set_json(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set a JSON value in cache with TTL."""
        try:
            self._get_client().setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            logger.warning(f"Failed to set JSON in cache: {e}")
            return False

    # ==================== Atomic Operations ====================

    def incr(self, key: str) -> Optional[int]:
        """Increment a counter."""
        try:
            return self._get_client().incr(key)
        except Exception as e:
            logger.warning(f"Failed to increment: {e}")
            return None

    def decr(self, key: str) -> Optional[int]:
        """Decrement a counter."""
        try:
            return self._get_client().decr(key)
        except Exception as e:
            logger.warning(f"Failed to decrement: {e}")
            return None


# Global cache instance
cache = RedisCache.get_instance()


def is_job_cancelled_cached(project_id: str) -> bool:
    """Check if job is cancelled using cache first, then database."""
    # Try cache first
    status = cache.get_job_status(f"project:{project_id}:latest_job")
    if status == "REVOKED":
        return True

    # Fall back to database
    from sqlmodel import Session
    from core.database import engine
    from core.models import Job, JobStatus

    try:
        with Session(engine) as session:
            job = session.query(Job).filter(
                Job.project_id == project_id
            ).order_by(Job.created_at.desc()).first()

            if job:
                # Update cache
                cache.set_job_status(f"project:{project_id}:latest_job", job.status.value)
                return job.status == JobStatus.REVOKED
    except Exception as e:
        logger.warning(f"Failed to check job status: {e}")

    return False
