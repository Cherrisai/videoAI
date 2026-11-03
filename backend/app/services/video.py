import os
import subprocess
from pathlib import Path
from app.core.config import get_settings


def probe_duration(path: str) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True, check=True, timeout=30)
    return max(0.0, float(result.stdout.strip()))


def extract_audio(path: str, video_id: str) -> str:
    # Compressed mono audio keeps long videos below hosted ASR upload limits.
    output = Path(get_settings().storage_dir) / video_id / "speech.mp3"
    subprocess.run(["ffmpeg", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k", str(output)], capture_output=True, check=True, timeout=600)
    return str(output)


def extract_frames(path: str, video_id: str, duration: float) -> list[dict]:
    root = Path(get_settings().storage_dir) / video_id / "frames"
    root.mkdir(parents=True, exist_ok=True)
    # Sample at most 12 evenly spaced points to bound storage and vision API usage.
    count = min(12, max(1, int(duration // 10) + 1))
    frames = []
    for i in range(count):
        seconds = min(duration, (i + 0.5) * duration / count)
        target = root / f"frame_{i:03d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-ss", str(seconds), "-i", path, "-frames:v", "1", "-vf", "scale='min(960,iw)':-2", str(target)], capture_output=True, check=True, timeout=60)
        frames.append({"timestamp": seconds, "path": str(target), "image": f"/media/{video_id}/frames/{target.name}"})
    return frames
