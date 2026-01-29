"""
Base client interfaces for multi-provider support.
"""
from abc import ABC, abstractmethod
from typing import Optional, Protocol, runtime_checkable
from enum import Enum


class ProviderType(str, Enum):
    """Supported provider types."""
    GOOGLE = "google"
    REPLICATE = "replicate"
    OPENAI = "openai"


@runtime_checkable
class ImageClientProtocol(Protocol):
    """Protocol for image generation clients."""
    
    def generate_image(
        self,
        prompt: str,
        reference_image_path: Optional[str] = None,
        style_preset: Optional[str] = None
    ) -> Optional[bytes]:
        """Generate an image from prompt."""
        ...


@runtime_checkable
class VideoClientProtocol(Protocol):
    """Protocol for video generation clients."""
    
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        camera_movement: Optional[str] = None,
        duration: float = 4.0
    ) -> Optional[bytes]:
        """Generate a video from an image."""
        ...


class BaseImageClient(ABC):
    """Abstract base class for image generation clients."""
    
    provider: ProviderType
    
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
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the client is properly configured and available."""
        pass


class BaseVideoClient(ABC):
    """Abstract base class for video generation clients."""
    
    provider: ProviderType
    
    @abstractmethod
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        camera_movement: Optional[str] = None,
        duration: float = 4.0,
        **kwargs
    ) -> bytes:
        """Generate a video from an image."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the client is properly configured and available."""
        pass
