"""Custom exception hierarchy for AnimeMatrix."""

import logging
from typing import Any

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
