import asyncio
import ipaddress
import json
import logging
import mimetypes
import os
import re
import socket
import uuid
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.api.schemas import ChatRequest, ChatResponse, SearchRequest, SearchResponse, PublicVideoURLRequest, YouTubeVideoRequest, RetryVideoRequest, TranscriptRequest, TranslationRequest, DubRequest
from app.core.config import get_settings
from app.core.errors import ProviderUnavailable
from app.db.database import get_db
from app.db.models import User, Video, Message, Job, LLMUsage, SearchConversation, SearchMessage
from app.providers.ai import AIProvider
from app.providers.youtube_video import YouTubeVideoProvider, normalize_youtube_url
from app.providers.speech import SpeechProvider, TranslationProvider, TTSProvider
from app.services.mcp import MCPTools, infer_lookup_kind
from app.services.processing import process_video
from app.services.video import extract_audio
from app.services.telemetry import record_usage, record_failure
from app.workers.queue import video_queue

router = APIRouter()
log = logging.getLogger(__name__)
LANGUAGES = ["English", "Tamil", "Hindi", "Kannada", "Telugu"]
BLOCKED_VIDEO_PLATFORMS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "googlevideo.com", "vimeo.com",
                          "tiktok.com", "instagram.com", "facebook.com", "dailymotion.com")
VIDEO_MIME_EXTENSIONS = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
                         "video/x-matroska": ".mkv", "video/x-msvideo": ".avi"}


def extract_source_details(text: str) -> list[dict[str, str]]:
    """Extract readable title, URL, and snippet fields from MCP search output."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None

    found: list[dict[str, str]] = []

    def visit(value):
        if isinstance(value, dict):
            url = next((item for key, item in value.items()
                        if key.lower() in {"url", "link", "source_url"}
                        and isinstance(item, str) and item.startswith("https://")), None)
            if url:
                title = next((item for key, item in value.items()
                              if key.lower() in {"title", "name"} and isinstance(item, str)), "")
                description = next((item for key, item in value.items()
                                    if key.lower() in {"description", "snippet", "content"} and isinstance(item, str)), "")
                found.append({"url": url, "title": title[:200], "description": description[:300]})
            else:
                for item in value.values():
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    if found:
        unique = {}
        for item in found:
            unique.setdefault(item["url"], item)
        return list(unique.values())
    urls = re.findall(r"https?://[^\s)\]>]+", text)
    return [{"url": url.rstrip("\"'`,.;}"), "title": "", "description": ""}
            for url in dict.fromkeys(urls)]


def extract_source_urls(text: str) -> list[str]:
    return [item["url"] for item in extract_source_details(text)]


async def validate_public_video_host(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "Use a public HTTPS link to a direct video file. Sign-in pages and embedded player links are not supported.")
    if parsed.port not in (None, 443):
        raise HTTPException(422, "Video links must use the standard HTTPS port.")
    host = parsed.hostname.rstrip(".").lower()
    if any(host == domain or host.endswith("." + domain) for domain in BLOCKED_VIDEO_PLATFORMS):
        raise HTTPException(422, "Platform page links are not fetched. Use an authorized direct video-file URL or upload the video.")
    try:
        loop = asyncio.get_running_loop()
        addresses = await asyncio.wait_for(loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM), timeout=5)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise HTTPException(422, "The video link must resolve only to a public internet host.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "Could not verify that video host as a public internet address.") from exc


@router.get("/health")
def health():
    return {"status": "ok", "service": "videosense-api"}


@router.post("/users")
def create_user(db: Session = Depends(get_db)):
    user = User(id=str(uuid.uuid4()), display_name="Local user")
    db.add(user)
    db.commit()
    return {"id": user.id, "display_name": user.display_name}


@router.post("/users/{user_id}/heartbeat")
def user_heartbeat(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User session not found")
    user.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "active", "last_seen_at": user.last_seen_at}


@router.get("/users/{user_id}/search-conversations")
def list_search_conversations(user_id: str, db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(404, "User session not found")
    conversations = (db.query(SearchConversation).filter_by(user_id=user_id)
                     .order_by(SearchConversation.updated_at.desc()).limit(50).all())
    return [{"id": item.id, "title": item.title, "updated_at": item.updated_at,
             "message_count": len(item.messages)} for item in conversations]


@router.get("/search-conversations/{conversation_id}/messages")
def get_search_messages(conversation_id: str, user_id: str, db: Session = Depends(get_db)):
    conversation = db.get(SearchConversation, conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(404, "Search conversation not found")
    return [{"id": message.id, "role": message.role, "content": message.content,
             "citations": message.citations, "provider": message.provider, "model": message.model,
             "latency_ms": message.latency_ms, "total_tokens": message.total_tokens,
             "created_at": message.created_at}
            for message in db.query(SearchMessage).filter_by(conversation_id=conversation_id)
            .order_by(SearchMessage.created_at).all()]


@router.get("/config")
async def config():
    s = get_settings()
    try:
        tools = await MCPTools().list_tools()
    except Exception:
        tools = []
    transcription_provider = ("Whisper-compatible" if s.whisper_api_key and s.whisper_base_url else
                              "Groq Whisper" if s.groq_api_key else None)
    return {"languages": LANGUAGES, "demo_mode": s.demo_mode, "chat_configured": bool(s.provider_options) or s.demo_mode,
            "providers": s.provider_options, "default_provider": s.default_provider,
            "youtube_video_configured": bool(s.gemini_api_key), "youtube_video_model": s.gemini_video_model,
            "transcription_configured": transcription_provider is not None,
            "transcription_provider": transcription_provider,
            "translation_languages": [x.strip() for x in s.translation_languages.split(",") if x.strip()],
            "tts_languages": [x.strip() for x in s.tts_languages.split(",") if x.strip()], "mcp_tools": tools}


@router.get("/users/{user_id}/videos")
def user_videos(user_id: str, db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(404, "User session not found")
    rows = db.query(Video).filter_by(user_id=user_id).order_by(Video.created_at.desc()).all()
    return [{"id": video.id, "filename": video.filename, "status": video.status, "created_at": video.created_at,
             "message_count": db.query(func.count(Message.id)).filter_by(video_id=video.id).scalar()} for video in rows]


@router.get("/dashboard/metrics")
def dashboard_metrics(user_id: str, video_id: str | None = None, db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(404, "User session not found")
    usage_query = db.query(LLMUsage).filter_by(user_id=user_id)
    videos_query = db.query(Video).filter_by(user_id=user_id)
    messages_query = db.query(func.count(Message.id)).join(Video).filter(Video.user_id == user_id)
    if video_id:
        if not db.query(Video.id).filter_by(id=video_id, user_id=user_id).first():
            raise HTTPException(404, "Video not found for this session")
        usage_query = usage_query.filter_by(video_id=video_id)
        videos_query = videos_query.filter_by(id=video_id)
        messages_query = messages_query.filter(Message.video_id == video_id)
    usage = usage_query.order_by(LLMUsage.created_at.desc()).all()
    videos = videos_query.count()
    messages_count = messages_query.scalar() or 0
    successful = [row for row in usage if row.status == "success"]
    latencies = sorted(row.latency_ms for row in successful)
    qwen = [row for row in usage if "qwen" in row.model.lower()]
    active_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    active_users = db.query(User).filter(User.last_seen_at >= active_cutoff).order_by(User.last_seen_at.desc()).all()
    hourly: dict[str, dict] = {}
    for row in reversed(usage):
        key = row.created_at.astimezone(timezone.utc).strftime("%m-%d %H:00")
        bucket = hourly.setdefault(key, {"hour": key, "calls": 0, "tokens": 0, "latency_ms": 0})
        bucket["calls"] += 1
        bucket["tokens"] += row.total_tokens
        bucket["latency_ms"] += row.latency_ms
    for bucket in hourly.values():
        bucket["avg_latency_ms"] = round(bucket["latency_ms"] / bucket["calls"])
    return {
        "videos": videos, "messages": messages_count, "llm_calls": len(usage),
        "successful_calls": len(successful), "failed_calls": len(usage) - len(successful),
        "tokens": sum(row.total_tokens for row in successful),
        "prompt_tokens": sum(row.prompt_tokens for row in successful),
        "completion_tokens": sum(row.completion_tokens for row in successful),
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "p95_latency_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0,
        "qwen": {"calls": len(qwen), "avg_latency_ms": round(sum(x.latency_ms for x in qwen) / len(qwen)) if qwen else 0,
                 "tokens": sum(x.total_tokens for x in qwen), "failures": sum(x.status != "success" for x in qwen)},
        "embeddings": {"configured": False, "calls": 0, "tokens": 0},
        "active_users": [{"session": row.id[:8], "display_name": row.display_name, "last_seen_at": row.last_seen_at} for row in active_users],
        "timeseries": list(hourly.values()),
        "traces": [{"id": row.id, "provider": row.provider, "model": row.model, "purpose": row.purpose,
                    "status": row.status, "latency_ms": row.latency_ms, "total_tokens": row.total_tokens,
                    "created_at": row.created_at} for row in usage[:100]],
    }


@router.post("/videos")
async def upload_video(file: UploadFile = File(...), user_id: str = Form(...), db: Session = Depends(get_db)):
    s = get_settings()
    if not db.get(User, user_id):
        raise HTTPException(404, "User session not found. Refresh the app and try again.")
    # Browsers may send Windows-style fake paths even when the API runs on Linux.
    client_name = (file.filename or "video").replace("\\.", ".").replace("\\", "/")
    name = Path(client_name).name
    extension = Path(name).suffix.lower()
    allowed = {x.strip().lower() for x in s.allowed_video_extensions.split(",")}
    if extension not in allowed:
        raise HTTPException(415, f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}")
    video_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    folder = Path(s.storage_dir) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("source" + extension)
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > s.upload_limit_bytes:
                    raise HTTPException(413, f"Video exceeds the {s.max_upload_mb} MB upload limit.")
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if not size:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded file is empty.")
    video = Video(id=video_id, user_id=user_id, filename=name, status="queued", status_message="Queued for processing")
    job = Job(id=job_id, video=video)
    db.add_all([video, job]); db.commit()
    try:
        video_queue.enqueue(process_video, video_id, str(target), job_id, job_id=job_id)
    except Exception as exc:
        video.status, video.status_message = "failed", "Could not queue processing. Confirm Redis is running and retry."
        job.status, job.error = "failed", str(exc)[:500]
        db.commit()
        raise HTTPException(503, video.status_message)
    return {"id": video_id, "status": video.status, "message": video.status_message}


@router.post("/videos/from-url")
async def upload_video_from_public_url(request: PublicVideoURLRequest, db: Session = Depends(get_db)):
    """Fetch an openly reachable direct video file; never extract from player pages."""
    settings = get_settings()
    if not db.get(User, request.user_id):
        raise HTTPException(404, "User session not found. Refresh the app and try again.")
    current_url = request.video_url.strip()
    video_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    folder = Path(settings.storage_dir) / video_id
    folder.mkdir(parents=True, exist_ok=True)
    target: Path | None = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10), follow_redirects=False) as client:
            downloaded = False
            for _ in range(6):
                await validate_public_video_host(current_url)
                async with client.stream("GET", current_url, follow_redirects=False) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise HTTPException(422, "The video host returned an invalid redirect.")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code != 200:
                        raise HTTPException(422, "This link is not publicly downloadable. Check sharing permissions or upload the file instead.")
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    original_name = Path(urlsplit(current_url).path).name or "linked-video"
                    extension = Path(original_name).suffix.lower()
                    if not extension:
                        extension = VIDEO_MIME_EXTENSIONS.get(media_type, "")
                    allowed = {item.strip().lower() for item in settings.allowed_video_extensions.split(",")}
                    if extension not in allowed:
                        raise HTTPException(415, "The public link must point directly to MP4, MOV, MKV, WebM, or AVI video. Player pages are not supported.")
                    if media_type not in VIDEO_MIME_EXTENSIONS and media_type != "application/octet-stream":
                        raise HTTPException(415, "The link did not return a supported video file. Upload the video if this host serves a player page.")
                    declared_length = response.headers.get("content-length")
                    if declared_length and int(declared_length) > settings.upload_limit_bytes:
                        raise HTTPException(413, f"Video exceeds the {settings.max_upload_mb} MB upload limit.")
                    target = folder / ("source" + extension)
                    size = 0
                    with target.open("wb") as output:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > settings.upload_limit_bytes:
                                raise HTTPException(413, f"Video exceeds the {settings.max_upload_mb} MB upload limit.")
                            output.write(chunk)
                    if not size:
                        raise HTTPException(400, "The public video file is empty.")
                    downloaded = True
                    break
            if not downloaded:
                raise HTTPException(422, "The video link redirected too many times.")
    except HTTPException:
        if target:
            target.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        raise
    except httpx.RequestError as exc:
        if target:
            target.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        log.info("Public video fetch failed for session %s", request.user_id[:8])
        raise HTTPException(422, "Could not fetch that public video link. Verify it is a direct HTTPS file URL, or upload the file.") from exc
    except (ValueError, OSError) as exc:
        if target:
            target.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        raise HTTPException(422, "Could not save the linked video. Upload the file or verify its size and format.") from exc
    name = Path(urlsplit(current_url).path).name or ("linked-video" + target.suffix)
    video = Video(id=video_id, user_id=request.user_id, filename=name, status="queued", status_message="Public video fetched and queued for processing")
    job = Job(id=job_id, video=video)
    db.add_all([video, job])
    db.commit()
    try:
        video_queue.enqueue(process_video, video_id, str(target), job_id, job_id=job_id)
    except Exception as exc:
        video.status, video.status_message = "failed", "Could not queue processing. Confirm Redis is running and retry."
        job.status, job.error = "failed", str(exc)[:500]
        db.commit()
        raise HTTPException(503, video.status_message)
    return {"id": video_id, "status": video.status, "message": video.status_message}


@router.post("/videos/youtube")
def add_public_youtube_video(request: YouTubeVideoRequest, db: Session = Depends(get_db)):
    """Register a public YouTube URL for direct, provider-authorized video analysis."""
    user = db.get(User, request.user_id)
    if not user:
        raise HTTPException(404, "User session not found. Refresh the app and try again.")
    if not get_settings().gemini_api_key:
        raise HTTPException(
            503,
            "Public YouTube chat is not configured. Add GEMINI_API_KEY in .env and restart with `docker compose up --build -d`. Uploaded videos can still use your configured Groq/OpenAI provider.",
        )
    try:
        source_url = normalize_youtube_url(request.video_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id, user_id=user.id, filename=f"YouTube video · {source_url.rsplit('=', 1)[-1]}",
        source_type="youtube", source_url=source_url, status="ready",
        status_message="Public YouTube link saved. Gemini analyzes the video when you ask a question.",
    )
    db.add(video)
    db.commit()
    return {"id": video.id, "status": video.status, "message": video.status_message}


@router.get("/videos/{video_id}")
def get_video(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return {"id": video.id, "filename": video.filename, "status": video.status, "message": video.status_message,
            "duration_seconds": video.duration_seconds, "scenes": video.scenes, "transcript": video.transcript, "translations": video.translations,
            "source_type": video.source_type, "source_url": video.source_url}


@router.post("/videos/{video_id}/retry")
def retry_video(video_id: str, request: RetryVideoRequest, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video or video.user_id != request.user_id:
        raise HTTPException(404, "Video not found for this session")
    if video.status != "failed":
        raise HTTPException(409, "Only failed video analysis can be retried.")
    source = Path(get_settings().storage_dir) / video_id / ("source" + Path(video.filename).suffix.lower())
    if not source.is_file():
        raise HTTPException(404, "The uploaded video file is no longer available. Upload it again to continue.")
    job_id = str(uuid.uuid4())
    job = Job(id=job_id, video_id=video_id)
    video.status, video.status_message = "queued", "Retry queued; checking the uploaded video and provider availability."
    db.add(job)
    db.commit()
    try:
        video_queue.enqueue(process_video, video_id, str(source), job_id, job_id=job_id)
    except Exception as exc:
        video.status, video.status_message = "failed", "Could not queue analysis retry. Confirm Redis is running and try again."
        job.status, job.error = "failed", str(exc)[:500]
        db.commit()
        raise HTTPException(503, video.status_message) from exc
    return {"id": video_id, "status": video.status, "message": video.status_message}


@router.get("/videos/{video_id}/source")
def source_video(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    path = Path(get_settings().storage_dir) / video_id / ("source" + Path(video.filename).suffix.lower())
    if not path.is_file():
        raise HTTPException(404, "Original video is unavailable")
    return FileResponse(path, media_type=mimetypes.guess_type(video.filename)[0] or "application/octet-stream", filename=video.filename)


@router.get("/videos/{video_id}/messages")
def messages(video_id: str, db: Session = Depends(get_db)):
    if not db.get(Video, video_id):
        raise HTTPException(404, "Video not found")
    rows = db.query(Message).filter_by(video_id=video_id).order_by(Message.created_at).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "citations": m.citations, "language": m.language,
             "provider": m.provider, "model": m.model, "latency_ms": m.latency_ms,
             "total_tokens": m.total_tokens, "created_at": m.created_at} for m in rows]


def _cached_youtube_evidence(history: list[dict]) -> str:
    """Build a modest local evidence cache from previous grounded YouTube answers."""
    notes = []
    current_question = ""
    for message in history:
        if message.get("role") == "user":
            current_question = str(message.get("content", ""))[:500]
        elif message.get("role") == "assistant":
            content = str(message.get("content", "")).strip()
            lower = content.lower()
            if not content or any(marker in lower for marker in (
                "gemini did not finish", "could not analyze this link", "temporarily over its request limit",
                "provider request failed", "demo mode:", "the video does not establish the answer",
            )):
                continue
            if current_question and ("[" in content or "video" in lower or "scene" in lower):
                notes.append(f"Earlier question: {current_question}\nGrounded answer: {content[:1800]}")
    return "\n\n".join(notes[-8:])[:12000]


def _successful_youtube_history(prior: list[Message]) -> list[dict]:
    """Keep complete grounded turns; omit saved provider failure messages on retries."""
    turns: list[dict] = []
    pending_question: str | None = None
    failure_markers = (
        "gemini did not finish analyzing", "gemini could not analyze",
        "gemini's video service returned", "gemini is temporarily over",
        "i couldn't analyze this turn", "videoai could not complete this request",
    )
    for message in prior:
        if message.role == "user":
            pending_question = message.content
        elif message.role == "assistant":
            answer = message.content.strip()
            if any(marker in answer.lower() for marker in failure_markers):
                pending_question = None
                continue
            if pending_question:
                turns.extend((
                    {"role": "user", "content": pending_question},
                    {"role": "assistant", "content": answer},
                ))
            pending_question = None
    return turns[-16:]


@router.delete("/videos/{video_id}/messages")
def delete_conversation(video_id: str, user_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video or video.user_id != user_id:
        raise HTTPException(404, "Conversation not found")
    count = db.query(Message).filter_by(video_id=video_id).delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


@router.delete("/videos/{video_id}/messages/{message_id}")
def delete_message(video_id: str, message_id: str, user_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    message = db.get(Message, message_id)
    if not video or video.user_id != user_id or not message or message.video_id != video_id:
        raise HTTPException(404, "Message not found")
    db.delete(message)
    db.commit()
    return {"deleted": 1}


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, db: Session = Depends(get_db)):
    """Search and continue a durable web conversation grounded in saved MCP evidence."""
    if request.language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported answer language. Choose one of: {', '.join(LANGUAGES)}")
    user = db.get(User, request.user_id)
    if not user:
        raise HTTPException(404, "User session not found")
    selected_provider = request.provider
    if selected_provider and selected_provider not in get_settings().provider_options:
        raise HTTPException(400, "That LLM provider is not configured. Add its API key in .env first.")

    conversation = None
    if request.conversation_id:
        conversation = db.get(SearchConversation, request.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(404, "Search conversation not found")
    else:
        conversation = SearchConversation(
            id=str(uuid.uuid4()), user_id=user.id,
            title=request.question[:120].strip() or "Web search",
        )
        db.add(conversation)
        db.commit()

    prior = (db.query(SearchMessage).filter_by(conversation_id=conversation.id)
             .order_by(SearchMessage.created_at).all())
    history = [{"role": message.role, "content": message.content} for message in prior[-10:]]
    prior_evidence = next((message.evidence for message in reversed(prior) if message.role == "assistant" and message.evidence), "")
    lookup_kind = infer_lookup_kind(request.question)
    if not prior and not lookup_kind:
        lookup_kind = "web"

    lookup_results: list[dict] = []
    lookup_error = None
    if lookup_kind:
        try:
            lookup_results = await MCPTools().lookup(request.question, lookup_kind)
        except Exception as exc:
            log.exception("Standalone MCP search failed for user id %s", user.id)
            lookup_error = f"{type(exc).__name__}: {str(exc)[:240]}"

    current_evidence = "\n".join(
        f"External lookup ({item['server']}/{item['tool']}): {item['text']}" for item in lookup_results
    )
    evidence = "\n\n".join(part for part in (prior_evidence, current_evidence) if part)
    if lookup_error:
        evidence += f"\nExternal search failed ({lookup_error}). Do not invent search results."
    citations = []
    for item in lookup_results:
        for source in extract_source_details(item["text"]):
            citations.append({"source": f"{item['server']} / {item['tool']}", **source})
    citations = list({item["url"]: item for item in citations}.values())[:20]

    user_message = SearchMessage(id=str(uuid.uuid4()), conversation_id=conversation.id,
                                 role="user", content=request.question)
    db.add(user_message)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    ai = AIProvider(selected_provider)
    llm_result = None
    started = time.perf_counter()
    if ai.configured and evidence:
        try:
            llm_result = await ai.answer(request.question, request.language, evidence, history)
            answer = llm_result.text
        except Exception as exc:
            log.exception("Standalone search answer generation failed for user id %s", user.id)
            config = get_settings().provider_options.get(ai.provider or "", {})
            record_failure(db, ai.provider or "unknown", config.get("chat_model", "unknown"), "external_search",
                           user.id, None, int((time.perf_counter() - started) * 1000))
            answer = (f"The answer model failed ({type(exc).__name__}). "
                      "Your search evidence and source links are saved; try a follow-up or check Settings.")
    elif evidence:
        answer = f"I found {len(citations)} source link(s). Open the links below, or configure an answer model to ask follow-up questions."
    elif lookup_kind:
        status = f" ({lookup_error})" if lookup_error else ""
        answer = f"No external results were returned{status}. Check the Brave API key, quota, and MCP connection."
    else:
        answer = "I don’t have earlier search evidence for this conversation. Ask me to search the web or share a link first."

    assistant_message = SearchMessage(
        id=str(uuid.uuid4()), conversation_id=conversation.id, role="assistant", content=answer,
        citations=citations, evidence=evidence,
        provider=llm_result.provider if llm_result else None,
        model=llm_result.model if llm_result else None,
        latency_ms=llm_result.latency_ms if llm_result else None,
        prompt_tokens=llm_result.prompt_tokens if llm_result else 0,
        completion_tokens=llm_result.completion_tokens if llm_result else 0,
        total_tokens=llm_result.total_tokens if llm_result else 0,
    )
    db.add(assistant_message)
    conversation.updated_at = datetime.now(timezone.utc)
    if llm_result:
        record_usage(db, llm_result, "external_search", user.id, None)
    db.commit()
    return SearchResponse(answer=answer, citations=citations, demo=bool(llm_result and llm_result.provider == "demo"),
                          conversation_id=conversation.id)


@router.post("/videos/{video_id}/chat", response_model=ChatResponse)
async def chat(video_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    if request.language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported answer language. Choose one of: {', '.join(LANGUAGES)}")
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.status != "ready":
        raise HTTPException(409, f"Video is {video.status}: {video.status_message}")
    prior = db.query(Message).filter_by(video_id=video_id).order_by(Message.created_at).all()
    evidence_parts, citations = [], []
    for scene in video.scenes:
        timestamp = float(scene.get("timestamp", 0))
        stamp = f"{int(timestamp//60):02d}:{int(timestamp%60):02d}"
        evidence_parts.append(f"[{stamp}] {scene.get('description', '')}")
        citations.append({"timestamp": timestamp, "image": scene.get("image"), "description": scene.get("description", "")})
    for segment in video.transcript:
        evidence_parts.append(f"[{int(segment['start']//60):02d}:{int(segment['start']%60):02d}] Transcript: {segment['text']}")
    lookup_results = []
    lookup_error = None
    external_citations = []
    lookup_kind = infer_lookup_kind(request.question)
    if lookup_kind:
        try:
            lookup_query = request.question
            if lookup_kind == "product":
                # Include only extracted, timestamped scene descriptions so a web
                # search can find candidate items without pretending to identify a brand.
                scene_summary = "; ".join(
                    f"{float(scene.get('timestamp', 0)):.0f}s {scene.get('description', '')}"
                    for scene in video.scenes[:6]
                    if scene.get("description")
                )
                lookup_query = f"Product pages matching this request: {request.question}. Video scene clues: {scene_summary}"
            elif lookup_kind == "video":
                # Search can find public video pages, but does not make them
                # downloadable by this app or bypass their host's access rules.
                scene_summary = "; ".join(
                    str(scene.get("description", ""))
                    for scene in video.scenes[:4]
                    if scene.get("description")
                )
                lookup_query = f"{request.question}. Video content clues: {scene_summary}"
            lookup_results = await MCPTools().lookup(lookup_query, lookup_kind)
            evidence_parts.extend(f"External lookup ({item['server']}/{item['tool']}): {item['text']}" for item in lookup_results)
            for item in lookup_results:
                for source in extract_source_details(item["text"]):
                    external_citations.append({"source": f"{item['server']} / {item['tool']}", **source})
        except Exception as exc:
            # Keep the failure visible to the user while preserving video chat.
            log.exception("Configured MCP lookup failed")
            lookup_error = f"{type(exc).__name__}: {str(exc)[:240]}"
    if lookup_kind and not lookup_results:
        detail = f" Provider error: {lookup_error}." if lookup_error else ""
        evidence_parts.append(
            "External lookup status: no usable results were returned for this request."
            + detail
            + " Tell the user that external search did not return results; do not claim that searching is forbidden or that a provider restriction blocked you."
        )
    history = (
        _successful_youtube_history(prior)
        if video.source_type == "youtube"
        else [{"role": m.role, "content": m.content} for m in prior]
    )
    selected_provider = request.provider
    if video.source_type != "youtube" and selected_provider and selected_provider not in get_settings().provider_options:
        raise HTTPException(400, "That LLM provider is not configured. Add its API key in .env first.")
    ai = AIProvider(selected_provider)
    started = time.perf_counter()
    vision_evidence = any(scene.get("image") for scene in video.scenes)
    try:
        if video.source_type == "youtube":
            if not video.source_url:
                raise HTTPException(422, "This YouTube video link is missing. Add the public link again.")
            if not video.youtube_evidence:
                video.youtube_evidence = _cached_youtube_evidence(history)
            if video.youtube_evidence:
                evidence_parts.append("Timestamped YouTube evidence index:\n" + video.youtube_evidence)
                if ai.configured:
                    result = await ai.answer(request.question, request.language, "\n".join(evidence_parts), history)
                else:
                    result = await YouTubeVideoProvider().answer_from_evidence(
                        request.question, request.language, "\n".join(evidence_parts), history,
                    )
            else:
                result = await YouTubeVideoProvider().answer(
                    video.source_url, request.question, request.language, history, "\n".join(evidence_parts),
                )
        elif vision_evidence:
            result = await ai.answer_video(
                request.question, request.language, "\n".join(evidence_parts), history,
                video.scenes, video_id,
            )
        else:
            result = await ai.answer(request.question, request.language, "\n".join(evidence_parts), history)
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        log.exception("LLM request failed for video id %s", video_id)
        config = get_settings().provider_options.get(ai.provider or "", {})
        failed_provider = "gemini" if video.source_type == "youtube" else (ai.provider or "unknown")
        failed_model = get_settings().gemini_video_model if video.source_type == "youtube" else config.get("vision_model" if vision_evidence else "chat_model", "unknown")
        record_failure(db, failed_provider, failed_model, "video_chat", video.user_id,
                       video_id, int((time.perf_counter() - started) * 1000))
        if video.source_type == "youtube" and isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status == 429:
                answer = "Gemini is temporarily over its request limit. Your question is saved; wait for the quota window to reset or check the Gemini API quota, then ask again."
            elif status in (401, 403):
                answer = "Gemini did not authorize this request. Check GEMINI_API_KEY, API access, and model availability in Google AI Studio. A video may also be inaccessible to Gemini; upload an authorized file as a fallback."
            elif status in (400, 404):
                answer = "Gemini could not access this YouTube video. It must be publicly accessible and supported by Gemini; private, unlisted, removed, age-restricted, or region-restricted videos may fail. Upload an authorized video file to continue."
            elif status in (500, 502, 503, 504):
                answer = f"Gemini's video service returned a temporary {status} error. Your question is saved; retry shortly. Your API key is configured, and this response came from the provider."
            else:
                answer = "Gemini could not analyze this link right now. Your question is saved; retry shortly or upload an authorized video file."
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="user", content=request.question,
                           language=request.language))
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="assistant", content=answer,
                           citations=[], language=request.language, provider=failed_provider, model=failed_model,
                           latency_ms=int((time.perf_counter() - started) * 1000)))
            db.commit()
            return ChatResponse(answer=answer, citations=[])
        if video.source_type == "youtube" and isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            answer = (
                "Gemini accepted the video but did not finish its analysis within four minutes. "
                "Your video and question are saved. Retry shortly; overview requests now use a faster model "
                "and sample fewer frames to reduce processing time and token use."
            )
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="user", content=request.question,
                           language=request.language))
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="assistant", content=answer,
                           citations=[], language=request.language, provider=failed_provider, model=failed_model,
                           latency_ms=int((time.perf_counter() - started) * 1000)))
            db.commit()
            return ChatResponse(answer=answer, citations=[])
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            answer = (
                "I couldn't analyze this turn because the vision provider is temporarily rate-limited. "
                "Your video and chat are saved. You can continue the conversation; visual answers will work "
                "again when the provider accepts requests. If this continues, check its quota or select another "
                "configured vision model."
            )
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="user", content=request.question,
                           language=request.language))
            db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="assistant", content=answer,
                           citations=[], language=request.language, provider=failed_provider, model=failed_model,
                           latency_ms=int((time.perf_counter() - started) * 1000)))
            db.commit()
            return ChatResponse(answer=answer, citations=[])
        db.commit()
        raise HTTPException(502, "The configured LLM provider request failed. Check its key, endpoint, and model in Settings.") from exc
    record_usage(db, result, "video_chat", video.user_id, video_id)
    if video.source_type == "youtube" and result.evidence_summary:
        video.youtube_evidence = result.evidence_summary
    answer = result.text
    if lookup_kind and not lookup_results:
        search_status = (
            f"External search failed ({lookup_error}). Check the Brave API key, quota, and MCP connection."
            if lookup_error
            else "No external search results were returned. Check the Brave API key, quota, and MCP connection."
        )
        answer = f"{search_status}\n\n" + answer
    cited_times = [int(minutes) * 60 + int(seconds) for minutes, seconds in re.findall(r"\[(\d{1,2}):(\d{2})\]", answer)]
    if video.source_type == "youtube" and video.source_url:
        citations = []
        for second in dict.fromkeys(cited_times):
            stamp = f"{second // 60:02d}:{second % 60:02d}"
            separator = "&" if "?" in video.source_url else "?"
            citations.append({"timestamp": second, "url": f"{video.source_url}{separator}t={second}s",
                              "title": f"Open YouTube at {stamp}", "description": "Timestamp cited by Gemini"})
    else:
        citations = [min(citations, key=lambda item: abs(float(item["timestamp"]) - time)) for time in cited_times] if cited_times and citations else []
    citations.extend(external_citations)
    db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="user", content=request.question, language=request.language))
    db.add(Message(id=str(uuid.uuid4()), video_id=video_id, role="assistant", content=answer, citations=citations, language=request.language,
                   provider=result.provider, model=result.model, latency_ms=result.latency_ms, prompt_tokens=result.prompt_tokens,
                   completion_tokens=result.completion_tokens, total_tokens=result.total_tokens))
    db.commit()
    return ChatResponse(answer=answer, citations=citations, demo=result.provider == "demo")


@router.post("/videos/{video_id}/transcript")
async def transcribe(video_id: str, request: TranscriptRequest, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    path = Path(get_settings().storage_dir) / video_id / ("source" + Path(video.filename).suffix.lower())
    try:
        audio_path = extract_audio(str(path), video_id)
        transcript = await SpeechProvider().transcribe(audio_path)
        video.transcript = transcript; db.commit()
        return {"transcript": transcript}
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        log.exception("Transcript provider error")
        raise HTTPException(502, "Transcription provider failed. Check endpoint configuration and logs.") from exc
    finally:
        (Path(get_settings().storage_dir) / video_id / "speech.wav").unlink(missing_ok=True)


@router.post("/videos/{video_id}/translation")
async def translate(video_id: str, request: TranslationRequest, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if not video.transcript:
        raise HTTPException(409, "Transcribe the video before translating it.")
    if request.target_language not in LANGUAGES:
        raise HTTPException(422, f"Unsupported language. Choose one of: {', '.join(LANGUAGES)}")
    try:
        translated = await TranslationProvider().translate(video.transcript, request.target_language)
        video.translations = {**(video.translations or {}), request.target_language: translated}
        db.commit()
        return {"transcript": translated, "target_language": request.target_language}
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        log.exception("Translation provider error")
        raise HTTPException(502, "Translation provider failed. Check endpoint configuration and logs.") from exc


@router.post("/videos/{video_id}/dub")
async def dub(video_id: str, request: DubRequest, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    transcript = video.transcript
    if not transcript:
        raise HTTPException(409, "Transcribe the video before generating dubbed audio.")
    try:
        translated = await TranslationProvider().translate(transcript, request.target_language)
        output = Path(get_settings().storage_dir) / video_id / f"dub-{request.target_language.lower()}.mp3"
        await TTSProvider().synthesize(translated, request.target_language, str(output))
        return {"audio_url": f"/api/videos/{video_id}/dub/audio?language={request.target_language}"}
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        log.exception("Dub provider error")
        raise HTTPException(502, "Dub generation provider failed. Check endpoint configuration and logs.") from exc


@router.get("/videos/{video_id}/dub/audio")
def dub_audio(video_id: str, language: str):
    path = Path(get_settings().storage_dir) / video_id / f"dub-{language.lower()}.mp3"
    if not path.is_file():
        raise HTTPException(404, "Dubbed audio is not ready")
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


