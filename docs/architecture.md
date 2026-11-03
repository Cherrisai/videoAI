# Architecture

## Request flow

1. Streamlit creates a local user record once per browser session, then sends its ID with a multipart video upload to FastAPI. FastAPI validates the user and filename extension and streams the file into a per-video directory on the shared Docker volume, enforcing the configured byte limit.
2. The API persists a video row and job row in PostgreSQL, then queues a short RQ task in Redis. The upload request returns immediately with the video ID.
3. The worker probes duration and extracts up to twelve evenly spaced JPEG frames with FFmpeg. One best-effort vision request describes up to three representative moments for the Moments tab. Provider failures do not fail the upload; frame references and timestamps are still saved to PostgreSQL.
4. Streamlit polls the video resource and renders status, scene summaries, and sampled frames. Follow-up questions are sent to the chat endpoint. The API loads stored conversation history, scene text, timestamped transcript, and sampled frame images. The configured vision-capable model answers from those image and text inputs. This supports visual counting questions, with counts reported per sampled timestamp; sparse frames cannot reliably track unique objects across the whole video. Rate-limited turns are saved in chat with an honest status message so the conversation can continue.
5. Transcription, translation, and TTS use separate adapters and endpoints. The transcript retains segment timestamps; translation preserves timing metadata; TTS produces downloadable audio. Each feature is independently configured.
6. When a question indicates an external lookup, the MCP boundary may call only explicitly allowed tools exposed by configured stdio servers. MCP output is added as external evidence and source URLs are rendered as links. No MCP connection is required for video chat.
7. The configured provider response supplies token usage where available. The API stores provider, model, purpose, status, request latency, and token counts in an `llm_usage` table without storing prompt text. The dashboard queries this table and the user's last-seen timestamp. Embedding calls are not present because this version has no embedding pipeline.

## Key decisions

- **Redis/RQ:** RQ is intentionally simpler to explain than a distributed workflow framework and is enough for one local worker. Redis contains transient queue state; PostgreSQL is the durable source of video, conversation, and job metadata.
- **PostgreSQL:** SQLAlchemy models keep persistence explicit. Tables are initialized at API startup for a one-command first run; production schema changes should move to Alembic migrations.
- **Shared volume:** API and worker share uploaded media and extracted frames. This avoids sending large video bytes through Redis. A horizontally scaled deployment would replace this with object storage.
- **Evidence limits:** Upload processing samples up to twelve frames and captions three representative moments. Question-time visual answers attach at most three frames for Groq Qwen, which has a three-image request limit, and at most eight for other configured vision models. The prompt asks for concise answers, timestamps, and an explicit insufficient-evidence response. Counts are per frame; repeated objects may appear in multiple samples, so a unique whole-video count is not claimed.
- **Provider boundaries:** Credentials/configuration are externalized. Provider adapters can be swapped without changing UI or persistence. Language claims for translation and TTS come from explicit configuration lists.
- **Groq option:** Groq uses its OpenAI-compatible chat endpoint. The default is Qwen 3.8 27B, which Groq lists as accepting text and images. Groq's Qwen vision endpoint accepts up to three images per request; the app honors that limit and retries only brief 429 throttles when the provider supplies a short `Retry-After` value.
- **Public YouTube links:** The UI recognizes supported public YouTube URL forms and calls `POST /videos/youtube`. FastAPI normalizes the video ID and saves only the URL and metadata. On each question, the Gemini adapter sends the URL and recent conversation to the official Gemini Interactions API. If a model returns 503 overload, it tries configured multimodal fallbacks (`gemini-3.6-flash`, then `gemini-3.5-flash-lite` by default). It does not fetch YouTube media itself. Provider access and YouTube eligibility can fail; upload remains the alternative.
- **Observability:** Provider-reported token counts and wall-clock latency power usage and Qwen panels. Embedding metrics are omitted because no embedding provider/pipeline is built.
- **History controls:** Individual chat messages or a conversation can be deleted. Deleting a message does not erase its aggregate provider trace.
- **Guardrails:** Upload extension/size are checked; filenames are reduced to their basename; the user confirms processing rights; no content is treated as executable instructions; MCP calls are opt-in and tool names are allowlisted. The app only passes normalized public YouTube URLs to Gemini and does not scrape or download YouTube media.
- **Local deployment:** Docker Compose runs Streamlit, API, worker, Redis, and PostgreSQL; Kubernetes is not required. The API health endpoint is `/api/health`.

## Main modules

- `frontend/app.py`: Streamlit upload, processing, chat, scene, transcript, and dub UI.
- `backend/app/api/`: FastAPI routes and Pydantic request/response contracts.
- `backend/app/services/`: FFmpeg processing, RQ task, and MCP orchestration.
- `backend/app/providers/`: model, transcription, translation, and TTS adapters.
- `backend/app/db/`: SQLAlchemy connection and durable models.
- `docker-compose.yml`: local service graph and shared volumes.
