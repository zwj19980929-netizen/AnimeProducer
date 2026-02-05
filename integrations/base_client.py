"""
Base client interfaces for multi-provider support.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class BaseImageClient(ABC):
    """Base interface for image generation clients."""
    
    provider_name: str = "base"
    
    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        reference_image_path: Optional[str] = None,
        style_preset: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Generate an image from prompt."""
        pass
    
    def health_check(self) -> bool:
        """Check if the provider is available."""
        return True


class BaseVideoClient(ABC):
    """Base interface for video generation clients."""

    provider_name: str = "base"

    @abstractmethod
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        image_url: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """Generate video from image.

        Args:
            image_path: Local image path (may be empty if image_url is provided)
            motion_prompt: Motion/camera movement description
            duration: Video duration in seconds
            image_url: Image URL (preferred over image_path if provided)
        """
        pass

    def health_check(self) -> bool:
        """Check if the provider is available."""
        return True


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class QuotaExceededError(ProviderError):
    """Raised when API quota is exceeded (429)."""
    pass


class AuthenticationError(ProviderError):
    """Raised when authentication fails."""
    pass


class BaseLLMClient(ABC):
    """Base interface for LLM clients."""
    
    provider_name: str = "base"
    
    @abstractmethod
    def generate_structured_output(
        self,
        prompt: str,
        pydantic_model,
        temperature: float = 0.2
    ):
        """Generate structured output using Pydantic model."""
        pass
    
    def health_check(self) -> bool:
        """Check if the provider is available."""
        return True
