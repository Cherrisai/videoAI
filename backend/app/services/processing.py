import asyncio
import logging
import subprocess

import httpx

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Job, Video
from app.providers.ai import AIProvider
from app.services.telemetry import record_failure, record_usage
from app.services.video import extract_frames, probe_duration

log = logging.getLogger(__name__)


def process_video(video_id: str, path: str, job_id: str) -> None:
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        job = db.get(Job, job_id)
        if not video or not job:
            return

        video.status = "processing"
        video.status_message = "Extracting duration and representative frames"
        job.status = "processing"
        db.commit()

        duration = probe_duration(path)
        frames = extract_frames(path, video_id, duration)
        # Summarize just three representative moments in one vision request. This
        # gives the Moments tab useful scene context while staying within Groq Qwen's
        # three-image request limit. Visual chat can inspect relevant frames again.
        sample_indices = sorted({round(i * (len(frames) - 1) / 2) for i in range(min(3, len(frames)))})
        representative = [frames[index] for index in sample_indices]
        ai = AIProvider()
        summaries: dict[str, str] = {}
        try:
            described = asyncio.run(ai.describe_frames(representative))
            summaries = {scene["image"]: scene["description"] for scene in described}
            for result in ai.usage_records:
                record_usage(db, result, "scene_analysis", video.user_id, video_id)
        except Exception as provider_error:
            log.warning("Optional scene summaries unavailable for video %s (%s)", video_id, type(provider_error).__name__)
            if ai.configured:
                config = get_settings().provider_options.get(ai.provider or "", {})
                record_failure(db, ai.provider or "unknown", config.get("vision_model", "unknown"),
                               "scene_analysis", video.user_id, video_id, 0)

        video.duration_seconds = int(duration)
        video.scenes = [
            {
                "timestamp": frame["timestamp"],
                "image": frame["image"],
                "description": summaries.get(frame["image"], "Sampled frame; scene summary unavailable for this moment."),
            }
            for frame in frames
        ]
        video.status = "ready"
        video.status_message = "Video ready. Ask a question to analyze its scenes and moments."
        job.status = "completed"
        db.commit()
    except Exception as exc:
        log.exception("Video processing failed for video id %s", video_id)
        video = db.get(Video, video_id)
        job = db.get(Job, job_id)
        if isinstance(exc, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            message = "FFmpeg could not decode this video. Try exporting it as a standard H.264 MP4 or MOV, then upload it again."
        else:
            message = "Video processing failed while preparing media. Check that the file is valid, then retry."
        if video:
            video.status, video.status_message = "failed", message
        if job:
            job.status, job.error = "failed", message
        db.commit()
    finally:
        db.close()
