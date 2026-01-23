"""
Video Generation Client for image-to-video conversion.
Supports camera movements and reverse video generation.
"""
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Literal

from config import settings

logger = logging.getLogger(__name__)

CameraMovement = Literal[
    "static",
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "rotate_cw",
    "rotate_ccw",
]


class VideoClient:
    """Video generation client for image-to-video conversion."""

    DEFAULT_FPS = 24
    DEFAULT_DURATION = 3.0

    def __init__(
        self,
        mock_mode: Optional[bool] = None,
    ):
        """
        Initialize video client.

        Args:
            mock_mode: Force mock mode. If None, auto-detect based on API key.
        """
        self._mock_mode = mock_mode
        self.api_key = settings.VIDEO_GEN_API_KEY
        self.api_url = settings.VIDEO_GEN_API_URL

    def _is_mock_mode(self) -> bool:
        if self._mock_mode is not None:
            return self._mock_mode
        return not self.api_key

    def _generate_mock_video(
        self,
        image_path: str,
        duration: float,
        camera_movement: str,
    ) -> bytes:
        """Generate a mock video from image using moviepy."""
        try:
            from moviepy import ImageClip

            path = Path(image_path)
            if not path.exists():
                logger.warning(f"Image not found: {image_path}, generating placeholder")
                return self._generate_placeholder_video(duration)

            clip = ImageClip(str(path), duration=duration)

            clip = self._apply_camera_movement(clip, camera_movement)

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp_path = tmp.name

            clip.write_videofile(
                tmp_path,
                fps=self.DEFAULT_FPS,
                codec="libx264",
                audio=False,
                logger=None,
            )
            clip.close()

            with open(tmp_path, "rb") as f:
                video_data = f.read()

            os.unlink(tmp_path)
            return video_data

        except ImportError:
            logger.error("moviepy not installed for mock video generation")
            return self._generate_placeholder_video(duration)
        except Exception as e:
            logger.error(f"Mock video generation failed: {e}")
            return self._generate_placeholder_video(duration)

    def _generate_placeholder_video(self, duration: float) -> bytes:
        """Generate a minimal placeholder video."""
        try:
            from moviepy import ColorClip
            import tempfile

            clip = ColorClip(size=(512, 512), color=(30, 30, 30), duration=duration)

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp_path = tmp.name

            clip.write_videofile(
                tmp_path,
                fps=self.DEFAULT_FPS,
                codec="libx264",
                audio=False,
                logger=None,
            )
            clip.close()

            with open(tmp_path, "rb") as f:
                video_data = f.read()

            os.unlink(tmp_path)
            return video_data

        except Exception as e:
            logger.error(f"Placeholder video generation failed: {e}")
            return b""

    def _apply_camera_movement(self, clip, movement: str):
        """Apply camera movement effect to clip."""
        from moviepy import vfx

        duration = clip.duration
        w, h = clip.size

        if movement == "zoom_in":
            def zoom_func(t):
                return 1 + 0.3 * (t / duration)
            return clip.resized(zoom_func).with_position("center")

        elif movement == "zoom_out":
            def zoom_func(t):
                return 1.3 - 0.3 * (t / duration)
            return clip.resized(zoom_func).with_position("center")

        elif movement == "pan_left":
            def position_func(t):
                x_offset = int(100 * (t / duration))
                return (-x_offset, 0)
            return clip.with_position(position_func)

        elif movement == "pan_right":
            def position_func(t):
                x_offset = int(100 * (t / duration))
                return (x_offset, 0)
            return clip.with_position(position_func)

        elif movement == "pan_up":
            def position_func(t):
                y_offset = int(80 * (t / duration))
                return (0, -y_offset)
            return clip.with_position(position_func)

        elif movement == "pan_down":
            def position_func(t):
                y_offset = int(80 * (t / duration))
                return (0, y_offset)
            return clip.with_position(position_func)

        elif movement == "rotate_cw":
            def rotate_func(t):
                return 15 * (t / duration)
            return clip.rotated(rotate_func)

        elif movement == "rotate_ccw":
            def rotate_func(t):
                return -15 * (t / duration)
            return clip.rotated(rotate_func)

        return clip

    def image_to_video(
        self,
        image_path: str,
        camera_movement: CameraMovement = "static",
        duration: float = DEFAULT_DURATION,
    ) -> bytes:
        """
        Convert a static image to video with optional camera movement.

        Args:
            image_path: Path to source image
            camera_movement: Type of camera movement to apply
            duration: Video duration in seconds

        Returns:
            Video data as bytes (MP4 format)
        """
        path = Path(image_path)
        if not path.exists():
            logger.error(f"Image not found: {image_path}")
            return self._generate_placeholder_video(duration)

        try:
            if self._is_mock_mode():
                logger.info(f"[MOCK] Generating video from: {image_path}")
                logger.info(f"[MOCK] Camera movement: {camera_movement}, Duration: {duration}s")
                return self._generate_mock_video(image_path, duration, camera_movement)

            logger.info(f"Generating video via API: {image_path}")
            return self._call_video_api(image_path, camera_movement, duration)

        except Exception as e:
            logger.error(f"Video generation failed: {e}")
            return self._generate_placeholder_video(duration)

    def _call_video_api(
        self,
        image_path: str,
        camera_movement: str,
        duration: float,
    ) -> bytes:
        """Call external video generation API."""
        import requests
        import base64

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "image": image_b64,
            "camera_movement": camera_movement,
            "duration": duration,
            "fps": self.DEFAULT_FPS,
        }

        try:
            response = requests.post(
                f"{self.api_url}/image-to-video",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()

            result = response.json()
            if "video_url" in result:
                video_response = requests.get(result["video_url"], timeout=60)
                video_response.raise_for_status()
                return video_response.content
            elif "video_b64" in result:
                return base64.b64decode(result["video_b64"])
            else:
                return response.content

        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    def reverse_video(self, video_data: bytes) -> bytes:
        """
        Generate a reversed version of the video.

        Args:
            video_data: Original video as bytes

        Returns:
            Reversed video as bytes
        """
        try:
            from moviepy import VideoFileClip
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_in:
                tmp_in.write(video_data)
                tmp_in_path = tmp_in.name

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_out:
                tmp_out_path = tmp_out.name

            clip = VideoFileClip(tmp_in_path)
            reversed_clip = clip.with_effects([lambda c: c.time_mirror()])

            reversed_clip.write_videofile(
                tmp_out_path,
                fps=self.DEFAULT_FPS,
                codec="libx264",
                audio=False,
                logger=None,
            )

            clip.close()
            reversed_clip.close()

            with open(tmp_out_path, "rb") as f:
                reversed_data = f.read()

            os.unlink(tmp_in_path)
            os.unlink(tmp_out_path)

            return reversed_data

        except ImportError:
            logger.error("moviepy not installed for video reversal")
            return video_data
        except Exception as e:
            logger.error(f"Video reversal failed: {e}")
            return video_data

    def reverse_video_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Create a reversed video file.

        Args:
            input_path: Path to input video
            output_path: Path for output (auto-generated if not provided)

        Returns:
            Path to reversed video file
        """
        input_p = Path(input_path)
        if not input_p.exists():
            raise FileNotFoundError(f"Video not found: {input_path}")

        if output_path is None:
            output_path = str(input_p.parent / f"{input_p.stem}_reversed{input_p.suffix}")

        with open(input_path, "rb") as f:
            video_data = f.read()

        reversed_data = self.reverse_video(video_data)

        with open(output_path, "wb") as f:
            f.write(reversed_data)

        logger.info(f"Saved reversed video to: {output_path}")
        return output_path

    def save_video(self, video_data: bytes, output_path: str) -> bool:
        """
        Save video data to file.

        Args:
            video_data: Video bytes
            output_path: Destination path

        Returns:
            True if saved successfully
        """
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "wb") as f:
                f.write(video_data)

            logger.info(f"Saved video to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save video: {e}")
            return False


video_client = VideoClient()
