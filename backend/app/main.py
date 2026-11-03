from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.database import Base, engine
from app.db import models  # noqa: F401
from pathlib import Path
from sqlalchemy import text

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(get_settings().storage_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # create_all initializes fresh databases; this additive step upgrades early local DBs.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS user_id VARCHAR(36) REFERENCES users(id)"))
        connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS translations JSON NOT NULL DEFAULT '{}'"))
        connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS gemini_interaction_id VARCHAR(128)"))
        connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS gemini_interaction_model VARCHAR(120)"))
        connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS youtube_evidence TEXT"))
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS provider VARCHAR(40)"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS model VARCHAR(120)"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS latency_ms INTEGER"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS total_tokens INTEGER NOT NULL DEFAULT 0"))
    yield


app = FastAPI(title="VideoAI API", version="0.1.0", description="Video processing, grounded chat, transcript, and dubbing API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")


@app.get("/media/{video_id}/frames/{filename}")
def frame(video_id: str, filename: str):
    if "/" in video_id or ".." in video_id or "/" in filename or ".." in filename:
        raise HTTPException(400, "Invalid frame path")
    path = Path(get_settings().storage_dir) / video_id / "frames" / filename
    if not path.is_file():
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/jpeg")
