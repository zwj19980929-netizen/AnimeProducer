"""
Replicate client for PixVerse v4 video generation.
"""
import logging
import time
from typing import Optional
import requests

from config import settings
from integrations.base_client import BaseVideoClient, QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class ReplicateVideoClient(BaseVideoClient):
    """Video generation client using Replicate's PixVerse v4."""
    
    provider_name: str = "replicate"
    
    def __init__(self):
        self.api_token = settings.REPLICATE_API_TOKEN
        self.base_url = "https://api.replicate.com/v1"
        self.model_version = "pixverse/pixverse-v4"  # PixVerse v4
        
        if not self.api_token:
            logger.warning("REPLICATE_API_TOKEN not set")
    
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        **kwargs
    ) -> bytes:
        """Generate video using PixVerse v4 on Replicate."""
        if not self.api_token:
            raise AuthenticationError("REPLICATE_API_TOKEN not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        # Read image and encode to base64
        import base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {
            "version": self.model_version,
            "input": {
                "image": f"data:image/png;base64,{image_b64}",
                "prompt": motion_prompt or "smooth camera movement",
                "duration": int(duration)
            }
        }
        
        try:
            # Create prediction
            response = requests.post(
                f"{self.base_url}/predictions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("Replicate rate limit exceeded")
            if response.status_code == 401:
                raise AuthenticationError("Replicate authentication failed")
            
            response.raise_for_status()
            prediction = response.json()
            prediction_id = prediction["id"]
            
            # Poll for completion
            for _ in range(120):  # Max 2 minutes
                poll_response = requests.get(
                    f"{self.base_url}/predictions/{prediction_id}",
                    headers=headers,
                    timeout=10
                )
                poll_data = poll_response.json()
                
                if poll_data["status"] == "succeeded":
                    video_url = poll_data["output"]
                    video_response = requests.get(video_url, timeout=60)
                    return video_response.content
                elif poll_data["status"] == "failed":
                    raise RuntimeError(f"Replicate prediction failed: {poll_data.get('error')}")
                
                time.sleep(1)
            
            raise RuntimeError("Replicate prediction timed out")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Replicate API error: {e}")
            raise
    
    def health_check(self) -> bool:
        """Check if Replicate API is accessible."""
        if not self.api_token:
            return False
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


replicate_video_client = ReplicateVideoClient()
