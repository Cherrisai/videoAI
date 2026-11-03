import uuid
from app.db.models import LLMUsage


def record_usage(db, result, purpose: str, user_id: str | None, video_id: str | None, status: str = "success") -> None:
    """Persist provider-reported token counts and wall-clock latency, without prompt content."""
    if result.provider == "demo":
        return
    db.add(LLMUsage(
        id=str(uuid.uuid4()), user_id=user_id, video_id=video_id,
        provider=result.provider, model=result.model, purpose=purpose, status=status,
        latency_ms=result.latency_ms, prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens, total_tokens=result.total_tokens,
    ))


def record_failure(db, provider: str, model: str, purpose: str, user_id: str | None, video_id: str | None, latency_ms: int) -> None:
    if provider == "demo":
        return
    db.add(LLMUsage(id=str(uuid.uuid4()), user_id=user_id, video_id=video_id, provider=provider or "unknown",
                    model=model or "unknown", purpose=purpose, status="failed", latency_ms=latency_ms))
