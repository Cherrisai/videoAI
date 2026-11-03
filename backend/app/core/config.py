from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://videosense:videosense@postgres:5432/videosense"
    redis_url: str = "redis://redis:6379/0"
    storage_dir: str = "/data"
    max_upload_mb: int = 500
    allowed_video_extensions: str = ".mp4,.mov,.mkv,.webm,.avi"
    demo_mode: bool = False
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_vision_model: str = "qwen/qwen3.8-27b"
    groq_chat_model: str = "qwen/qwen3.8-27b"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    vision_model: str = "gpt-4o-mini"
    chat_model: str = "gpt-4o-mini"
    custom_api_key: str = ""
    custom_base_url: str = ""
    custom_vision_model: str = ""
    custom_chat_model: str = ""
    gemini_api_key: str = ""
    gemini_video_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3.6-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    whisper_api_key: str = ""
    whisper_base_url: str = ""
    whisper_model: str = "whisper-1"
    translation_api_key: str = ""
    translation_base_url: str = ""
    translation_model: str = ""
    translation_languages: str = ""
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_model: str = ""
    tts_languages: str = ""
    mcp_servers_json: str = "[]"
    brave_api_key: str = ""

    @property
    def provider_options(self) -> dict[str, dict[str, str]]:
        options = {}
        if self.groq_api_key:
            options["groq"] = {"label": "Groq", "base_url": self.groq_base_url, "vision_model": self.groq_vision_model, "chat_model": self.groq_chat_model}
        if self.openai_api_key:
            options["openai"] = {"label": "OpenAI", "base_url": self.openai_base_url, "vision_model": self.vision_model, "chat_model": self.chat_model}
        if self.custom_api_key and self.custom_base_url:
            options["custom"] = {"label": "Other OpenAI-compatible", "base_url": self.custom_base_url, "vision_model": self.custom_vision_model, "chat_model": self.custom_chat_model}
        return options

    @property
    def default_provider(self) -> str | None:
        if self.llm_provider in self.provider_options:
            return self.llm_provider
        return next(iter(self.provider_options), None)

    @property
    def upload_limit_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
