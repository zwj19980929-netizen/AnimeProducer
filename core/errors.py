"""Custom exception hierarchy for AnimeMatrix."""

import logging
import time
import traceback
from functools import wraps
from typing import Any, Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)


class AnimeMatrixError(Exception):
    """Base exception for all AnimeMatrix errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        logger.error(f"{self.__class__.__name__}: {message}", extra={"details": self.details})

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message

    def to_dict(self) -> dict:
        """Convert error to dictionary for API responses."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }


class TransientError(AnimeMatrixError):
    """Transient error that can be retried.

    Examples: network timeouts, temporary service unavailability.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retry_after = retry_after


class PermanentError(AnimeMatrixError):
    """Permanent error that should not be retried.

    Examples: validation errors, missing required data, permission denied.
    """
    pass


class AssetMissingError(PermanentError):
    """Asset file or resource not found."""

    def __init__(
        self,
        asset_type: str,
        asset_id: str,
        path: str | None = None,
    ) -> None:
        details = {"asset_type": asset_type, "asset_id": asset_id}
        if path:
            details["path"] = path
        super().__init__(
            f"Asset not found: {asset_type} '{asset_id}'",
            details=details,
        )
        self.asset_type = asset_type
        self.asset_id = asset_id
        self.path = path


class ExternalAPIError(AnimeMatrixError):
    """Error from external API call."""

    def __init__(
        self,
        service: str,
        status_code: int | None = None,
        response_body: str | None = None,
        message: str | None = None,
    ) -> None:
        details: dict[str, Any] = {"service": service}
        if status_code is not None:
            details["status_code"] = status_code
        if response_body is not None:
            details["response_body"] = response_body[:500]  # Truncate long responses

        super().__init__(
            message or f"External API error from {service}",
            details=details,
        )
        self.service = service
        self.status_code = status_code
        self.response_body = response_body

    @property
    def is_retryable(self) -> bool:
        """Check if this error is likely transient and can be retried."""
        if self.status_code is None:
            return True  # Network error, likely transient
        return self.status_code in (429, 500, 502, 503, 504)


class ProjectNotFoundError(PermanentError):
    """Project with given ID not found."""

    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project not found: {project_id}", details={"project_id": project_id})
        self.project_id = project_id


class JobNotFoundError(PermanentError):
    """Job with given ID not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job not found: {job_id}", details={"job_id": job_id})
        self.job_id = job_id


class InvalidStateError(PermanentError):
    """Invalid state transition or operation not allowed in current state."""

    def __init__(
        self,
        message: str,
        current_state: str,
        expected_states: list[str] | None = None,
    ) -> None:
        details: dict[str, Any] = {"current_state": current_state}
        if expected_states:
            details["expected_states"] = expected_states
        super().__init__(message, details=details)
        self.current_state = current_state
        self.expected_states = expected_states


class RenderError(AnimeMatrixError):
    """Error during rendering process."""

    def __init__(
        self,
        shot_id: str,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = {"shot_id": shot_id, "stage": stage}
        if details:
            full_details.update(details)
        super().__init__(f"Render error at {stage}: {message}", details=full_details)
        self.shot_id = shot_id
        self.stage = stage


class ConfigurationError(PermanentError):
    """Configuration or environment error."""

    def __init__(self, message: str, config_key: str | None = None) -> None:
        details = {}
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, details=details)
        self.config_key = config_key


class RateLimitError(TransientError):
    """Rate limit exceeded."""

    def __init__(self, service: str, retry_after: int = 60) -> None:
        super().__init__(
            f"Rate limit exceeded for {service}",
            details={"service": service},
            retry_after=retry_after
        )
        self.service = service


class ValidationError(PermanentError):
    """Input validation error."""

    def __init__(self, field: str, message: str, value: Any = None) -> None:
        details = {"field": field}
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate long values
        super().__init__(f"Validation error for '{field}': {message}", details=details)
        self.field = field


# ==================== Retry Decorator ====================

def retry_on_error(
    max_retries: int = 3,
    retry_exceptions: Tuple[Type[Exception], ...] = (TransientError, ExternalAPIError),
    backoff_factor: float = 1.0,
    max_backoff: float = 60.0,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """Decorator to retry function on transient errors with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        retry_exceptions: Tuple of exception types to retry on
        backoff_factor: Base factor for exponential backoff
        max_backoff: Maximum backoff time in seconds
        on_retry: Optional callback called on each retry with (exception, attempt)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e

                    # Check if error is retryable
                    if isinstance(e, ExternalAPIError) and not e.is_retryable:
                        raise

                    if attempt < max_retries:
                        # Calculate backoff time
                        backoff = min(backoff_factor * (2 ** attempt), max_backoff)

                        # Use retry_after if available
                        if isinstance(e, TransientError) and e.retry_after:
                            backoff = min(e.retry_after, max_backoff)

                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {backoff:.1f}s due to: {e}"
                        )

                        if on_retry:
                            on_retry(e, attempt + 1)

                        time.sleep(backoff)
                    else:
                        raise
                except PermanentError:
                    # Don't retry permanent errors
                    raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e

                    if isinstance(e, ExternalAPIError) and not e.is_retryable:
                        raise

                    if attempt < max_retries:
                        backoff = min(backoff_factor * (2 ** attempt), max_backoff)

                        if isinstance(e, TransientError) and e.retry_after:
                            backoff = min(e.retry_after, max_backoff)

                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {backoff:.1f}s due to: {e}"
                        )

                        if on_retry:
                            on_retry(e, attempt + 1)

                        await asyncio.sleep(backoff)
                    else:
                        raise
                except PermanentError:
                    raise

            if last_exception:
                raise last_exception

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def format_exception(e: Exception) -> dict:
    """Format exception for logging or API response."""
    return {
        "error_type": type(e).__name__,
        "message": str(e),
        "traceback": traceback.format_exc(),
        "details": getattr(e, "details", {})
    }
