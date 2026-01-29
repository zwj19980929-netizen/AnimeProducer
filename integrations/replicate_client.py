"""
Replicate API client for PixVerse v4 video generation.
"""
import logging
import os
from typing import Optional

try:
    import replicate
except ImportError:
    replicate = None

from config import settings
from integrations.base_clients import BaseVideoClient, ProviderType

logger = logging.getLogger(__name__)


class ReplicateVideoClient(BaseVideoClient):
    """Replicate client for PixVerse v4 video generation."""
    
    provider = ProviderType.REPLICATE
    
    def __init__(self):
        self.api_token = getattr(settings, 'REPLICATE_API_TOKEN', None) or os.getenv('REPLICATE_API_TOKEN')
        self.model_id = "pixverse/pixverse-v4"
        
        if self.api_token and replicate:
            os.environ['REPLICATE_API_TOKEN'] = self.api_token
            logger.info("ReplicateVideoClient initialized")
        else:
            logger.warning("ReplicateVideoClient: API token not configured or replicate not installed")
    
    def is_available(self) -> bool:
        """Check if Replicate client is available."""
        return bool(self.api_token and replicate)
    
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        camera_movement: Optional[str] = None,
        duration: float = 4.0,
        **kwargs
    ) -> bytes:
        """
        Generate video using PixVerse v4 via Replicate.
        
        Args:
            image_path: Path to the input image
            motion_prompt: Motion description
            camera_movement: Camera movement type
            duration: Target duration in seconds
            
        Returns:
            Video bytes
        """
        if not self.is_available():
            raise RuntimeError("Replicate client not available (missing API token or library)")
        
        logger.info(f"🎬 [Replicate/PixVerse] Generating video from: {image_path}")
        
        prompt = motion_prompt or "Smooth animation"
        if camera_movement:
            prompt = f"{prompt}, {camera_movement} camera movement"
        
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            
            output = replicate.run(
                self.model_id,
                input={
                    "image": image_data,
                    "prompt": prompt,
                    "duration": min(int(duration), 5),
                    "quality": "high"
                }
            )
            
            import urllib.request
            if isinstance(output, str):
                with urllib.request.urlopen(output) as response:
                    return response.read()
            elif hasattr(output, 'read'):
                return output.read()
            else:
                raise RuntimeError(f"Unexpected output type: {type(output)}")
                
        except Exception as e:
            logger.error(f"❌ Replicate video generation failed: {e}")
            raise


replicate_video_client = ReplicateVideoClient()
