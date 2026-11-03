from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    language: str = "English"
    provider: str | None = None


class SearchRequest(ChatRequest):
    user_id: str = Field(min_length=1, max_length=36)
    conversation_id: str | None = Field(default=None, max_length=36)


class PublicVideoURLRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    video_url: str = Field(min_length=1, max_length=4096)


class YouTubeVideoRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    video_url: str = Field(min_length=1, max_length=4096)


class RetryVideoRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict]
    demo: bool = False


class SearchResponse(ChatResponse):
    conversation_id: str


class TranscriptRequest(BaseModel):
    pass


class TranslationRequest(BaseModel):
    target_language: str


class DubRequest(BaseModel):
    target_language: str
    preserve_original_audio: bool = False
