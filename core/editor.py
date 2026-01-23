from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import Loop
import os
from typing import List

def assemble_video(video_paths: List[str], audio_path: str, output_path: str):
    """
    Concatenates video clips and aligns them with an audio track.
    If video is shorter than audio, loop the video to match.
    If video is longer, it will be cut to match audio (implied by set_audio if not explicit, but loop is key).
    """
    try:
        # Load clips
        clips = [VideoFileClip(p) for p in video_paths]
        final_video_clip = concatenate_videoclips(clips)

        # Load Audio
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        video_duration = final_video_clip.duration

        print(f"Video Duration: {video_duration}s, Audio Duration: {audio_duration}s")

        # Logic: If Audio is longer, loop video. If Video is longer, cut video?
        # Requirement: "If audio is 5s, video is 3s, must slow-motion or loop"
        # We will loop for this demo.

        if video_duration < audio_duration:
            print("Video is shorter than audio. Looping video to match.")
            # New MoviePy v2 API
            final_video_clip = final_video_clip.with_effects([Loop(duration=audio_duration)])

        elif video_duration > audio_duration:
            print("Video is longer than audio. Clipping video.")
            final_video_clip = final_video_clip.subclipped(0, audio_duration)

        # Set audio
        final_video_clip = final_video_clip.with_audio(audio_clip)

        # Write output
        final_video_clip.write_videofile(output_path, fps=24)
        print(f"Successfully created: {output_path}")

    except Exception as e:
        print(f"Error assembling video: {e}")
    finally:
        # Clean up resources if needed
        pass
