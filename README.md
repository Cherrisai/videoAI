# VideoAI

VideoAI is a deployable video Q&A application. Streamlit provides the user interface, FastAPI handles uploads and chat, Redis queues long video jobs, PostgreSQL stores metadata and conversations, and FFmpeg extracts representative frames. Provider integrations are optional and report setup instructions when missing; there are no fabricated model, transcript, or search results.

## Start locally

Prerequisites: Docker Desktop or Docker Engine with the Compose plugin, and enough disk space for Docker images and uploaded videos. Copy `.env.example` to `.env`, then start the five services:

```sh
cp .env.example .env
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) for the app and [http://localhost:8000/docs](http://localhost:8000/docs) for the API. The health endpoint is [http://localhost:8000/api/health](http://localhost:8000/api/health). `docker compose down` stops services; named volumes retain uploaded video data and PostgreSQL records. Use `docker compose down -v` only when you intend to delete that data.

For real visual analysis of uploaded files, add `GROQ_API_KEY` in `.env` and restart. Groq is the default provider; the default vision and chat model is `qwen/qwen3.8-27b`. You can choose another configured provider from Settings. For public YouTube links, configure `GEMINI_API_KEY`; this uses Gemini's official YouTube URL input and is independent of Groq. Without provider keys, uploads and frame extraction still work, while the UI explains which analysis is unavailable. To explore the workflow with clearly marked sample descriptions and answers, set `DEMO_MODE=true`; demo content is never represented as model output.

Groq setup and model support: [OpenAI-compatible API](https://console.groq.com/docs/openai), [vision models](https://console.groq.com/docs/vision), and [supported models](https://console.groq.com/docs/models). Model availability and pricing can change; check Groq’s model page before estimating costs.

## Use the app

1. Upload MP4, MOV, MKV, WebM, or AVI up to `MAX_UPLOAD_MB` (default 500 MB), paste a public direct video-file URL, or paste a public YouTube watch/Shorts/youtu.be link when Gemini is configured. Confirm you have rights to process the video and audio.
2. Processing runs in an RQ worker. Refresh status until ready. FFmpeg records duration and samples at most twelve frames. A single scene-summary request uses up to three representative frames; if the provider is unavailable, the upload still completes and saved frames can be analyzed later in chat.
3. Ask follow-up questions in the video chat. The configured vision model inspects sampled timestamped frames directly, alongside saved scene summaries and transcript text. Answers cite frames. Visual counts are per sampled frame; sparse samples cannot establish a unique count across the entire clip or track objects between frames. Groq Qwen requests use at most three images per call; other providers use a conservative cap of eight.
4. In Transcript & dubbing, configure the separate ASR, translation, and TTS providers to access those controls. Confirm dubbing rights before generating audio. This version does not clone voices or mux dubbed audio into the original video.
5. Use **Usage dashboard** for recorded model calls, provider-reported token counts, measured latency, Qwen performance, request traces, and active local sessions. Embedding metrics are omitted because this build has no embedding pipeline.
6. Use **Message history** to delete individual messages or clear a conversation. **Settings** selects among configured LLM providers; API keys remain in `.env`.

Direct-file imports check the resolved host, redirects, content type, extension, and configured size limit. YouTube is handled separately: the app sends a normalized public video URL to Gemini without downloading or storing the video. Gemini's URL input may not access private, unlisted, removed, or region-restricted videos; upload a file you are authorized to process instead. TikTok, Instagram, sign-in pages, and other player pages are not fetched.

## Providers and language support

All credentials belong in the untracked `.env` file, never in source code or Streamlit state.

| Capability | Configuration | Behavior |
| --- | --- | --- |
| Visual analysis and chat (default) | `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_VISION_MODEL`, `GROQ_CHAT_MODEL` | OpenAI-compatible Groq chat completions. Default model is `qwen/qwen3.8-27b`; Groq documents image input support. |
| Public YouTube chat | `GEMINI_API_KEY`, `GEMINI_VIDEO_MODEL`, `GEMINI_FALLBACK_MODELS` | Gemini video URL input; default model is `gemini-3.8-flash`. On a 503 overload, it tries `gemini-3.6-flash` and `gemini-3.5-flash-lite` in order. This adapter is used for YouTube sources only. |
| Alternative OpenAI | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `VISION_MODEL`, `CHAT_MODEL` | OpenAI-compatible chat completions with image input. Choose a video/image-capable model supported by the endpoint. |
| Other compatible API | `CUSTOM_API_KEY`, `CUSTOM_BASE_URL`, `CUSTOM_VISION_MODEL`, `CUSTOM_CHAT_MODEL` | Connect another OpenAI-compatible provider. |
| Transcription | `GROQ_API_KEY` (or `WHISPER_API_KEY`, `WHISPER_BASE_URL`, `WHISPER_MODEL`) | Uses Groq Whisper Large v3 Turbo automatically when a Groq key is present; a custom Whisper-compatible endpoint takes precedence. The response should return `verbose_json` segments. |
| Translation | `TRANSLATION_API_KEY`, `TRANSLATION_BASE_URL`, `TRANSLATION_MODEL`, `TRANSLATION_LANGUAGES` | OpenAI-compatible chat endpoint. The UI lists only languages explicitly named in the comma-separated support list. |
| Text to speech | `TTS_API_KEY`, `TTS_BASE_URL`, `TTS_MODEL`, `TTS_LANGUAGES` | Endpoint accepts `{model,input,language,response_format}` and returns audio bytes. Language names are shown only when explicitly configured. |
| Web/place/image lookup | `BRAVE_API_KEY` or `MCP_SERVERS_JSON` | Brave's official MCP server is included in the API image. Place lookup depends on the Brave plan. Other stdio MCP servers can be explicitly configured in `MCP_SERVERS_JSON`. |

The UI offers English, Tamil, Hindi, Kannada, and Telugu as answer language choices. The selected answer language does not imply that your model provider supports it. Translation and TTS availability are independently controlled by the explicit language lists above. Provider endpoint request formats can differ; adapters are small modules under `backend/app/providers/` and may need adjustment for a specific service.

The dashboard only counts token usage reported by the provider. Measured latency is the application-side provider request duration. The app does not save prompts in telemetry traces. Active-session tracking records a generated local user ID and last-seen timestamp; there is no account authentication. Do not expose this local deployment to an untrusted network.

MCP lookup remains off until you configure a trusted server. To connect one:

1. Choose an MCP server that provides the lookup categories you need. Check its documentation for exact tool names and required arguments.
2. Make its executable and runtime available inside the API container. The stock API image intentionally includes no third-party MCP server.
3. For the included Brave MCP server, put your key in the ignored `.env` file as `BRAVE_API_KEY=your_key`. Restart with `docker compose up --build -d`; the API starts the official Brave server and exposes only its web, local/place, image, and video search tools. Since Brave has no product catalog tool, product questions fall back to web search and results are presented as likely matches. For other MCP servers, use the JSON configuration below; only names listed in `allow_tools` can be called.
4. Rebuild and restart Compose, then check the app's MCP tool status and `docker compose logs api` if discovery fails.

Example shape (replace the command, args, environment values, and tool names with the server's documented values):

```dotenv
MCP_SERVERS_JSON='[{"name":"my-search","transport":"stdio","command":"/opt/my-mcp-server","args":[],"env":{"SEARCH_API_KEY":"put-your-key-here"},"allow_tools":["web_search","place_search","image_search","product_search"]}]'
```

MCP server executables must be present in the API container image. Do not enable tools you do not trust, and do not commit `.env`.

## Architecture

See [docs/architecture.md](docs/architecture.md) for request flow and [docs/interview-guide.md](docs/interview-guide.md) for a plain-language project walkthrough. The FastAPI schema initializes PostgreSQL tables on startup (`Base.metadata.create_all`); this is suitable for the first local deployment. Use versioned Alembic migrations before evolving a shared or production database.

## Limitations and troubleshooting

- Processing extracts frames and duration; it does not infer semantics without a configured vision model. Frame sampling is capped at twelve images for bounded cost and storage, so details between samples may be missed.
- Uploads are saved on the shared Docker volume and associated with a generated local user record. There is no user authentication, retention scheduler, or secure multi-tenant isolation; keep this deployment local/private.
- Transcription, translation, TTS, and MCP providers are optional. Setup messages identify required environment variables. No voice cloning is implemented. Dubbed audio is downloadable, but replacing/mixing the original soundtrack is not implemented. Embedding search and embedding usage are not implemented.
- If the UI cannot reach the API, run `docker compose ps` and `docker compose logs api`. If processing is queued indefinitely, inspect `docker compose logs worker redis`. If files fail, try an MP4 and inspect `docker compose logs worker` for FFmpeg/provider errors.
- If port 8501 or 8000 is occupied, set `STREAMLIT_HOST_PORT` or `API_HOST_PORT` in `.env`. To increase the upload limit, change `MAX_UPLOAD_MB` in `.env`; ensure proxy and disk limits allow the same size.
- A missing API key does not disable unrelated upload and frame extraction functionality. A configured provider error is shown as a clear API error rather than a synthetic result.
