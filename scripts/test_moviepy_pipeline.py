import os
import sys
import numpy as np
from moviepy import ColorClip, AudioArrayClip

# Add root to sys.path
sys.path.append(os.getcwd())

from core.editor import assemble_video
from config import settings

def create_dummy_assets():
    """Generates dummy video and audio files for testing."""
    os.makedirs(settings.RAW_MATERIALS_DIR, exist_ok=True)

    # Create 3 dummy video clips (solid colors)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)] # Red, Green, Blue
    video_paths = []

    for i, color in enumerate(colors):
        filename = os.path.join(settings.RAW_MATERIALS_DIR, f"clip_{i}.mp4")
        # Create a 2-second clip of a solid color
        clip = ColorClip(size=(640, 480), color=color, duration=2.0)
        clip.write_videofile(filename, fps=24, logger=None)
        video_paths.append(filename)

    # Create a dummy audio clip (sine wave)
    # 10 seconds audio (longer than 2+2+2=6s video) to test looping
    duration = 10.0
    rate = 44100
    t = np.linspace(0, duration, int(duration * rate), endpoint=False)
    x = 0.5 * np.sin(2 * np.pi * 440 * t) # A440 tone
    audio = np.stack([x, x], axis=1) # Stereo

    audio_filename = os.path.join(settings.RAW_MATERIALS_DIR, "audio.mp3")
    audio_clip = AudioArrayClip(audio, fps=rate)
    audio_clip.write_audiofile(audio_filename, logger=None)

    return video_paths, audio_filename

def test_pipeline():
    print("Generating dummy assets...")
    video_paths, audio_path = create_dummy_assets()

    output_path = os.path.join(settings.OUTPUT_DIR, "final_demo.mp4")
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

    print("Assembling video...")
    assemble_video(video_paths, audio_path, output_path)

if __name__ == "__main__":
    test_pipeline()
