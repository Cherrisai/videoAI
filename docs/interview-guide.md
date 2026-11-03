# Interview guide

## What does VideoAI do?

It gives someone a place to upload a video, ask follow-up questions, and inspect the timestamped frames behind an answer. Speech transcription, translation, dubbing, and external lookups are optional integrations.

The interface uses a cherry-red theme and separates the workspace, usage dashboard, message history, and settings. A provider can be selected per browser session; API secrets stay in environment variables.

## How does a long video avoid freezing the interface?

The API stores the file, writes a job record to PostgreSQL, and adds work to Redis through RQ. It returns a video ID right away. A separate worker runs FFmpeg and model calls, then updates the job/video status. Streamlit can refresh status while work continues. The video itself stays on a shared volume instead of being copied into Redis.

## Why two databases?

PostgreSQL stores durable records: uploaded-video metadata, status, timestamped scenes/transcript, conversation messages, and jobs. Redis is the fast temporary queue used to hand work to the worker. Redis is not the long-term record of what the user asked.

## How is an answer grounded?

The API gathers sampled frames, timestamped transcript segments, recent chat turns, and image evidence for each video question. The vision model receives the images directly, so it can reason about people, objects, and actions. It reports counts by sampled timestamp and does not add repeated appearances into a unique whole-video total. The upload worker captions three representative moments in one request; Groq Qwen accepts at most three images per call, so the adapter honors that provider limit. Provider errors do not mark a valid upload as unreadable. Since only a small number of frames are sampled, the system should be candid when an event could have happened between samples.

## What is MCP doing?

MCP is a standard connection boundary for external tools. The app can inspect configured servers and invoke only tool names explicitly listed in each server's `allow_tools`. Search, place, image, and product lookup are optional and should return their own links. If no server is configured, video chat remains available without external lookup.

## How does Groq fit?

Groq is the default provider option because it offers an OpenAI-compatible API, so the same adapter can be reused by changing the key, base URL, and model. The default Qwen model can process text and image inputs; the worker extracts frames locally and the chat request attaches a capped set of frames for question-driven visual reasoning. This avoids spending image tokens before the user asks. OpenAI and custom compatible endpoints remain selectable.

## How are YouTube links handled?

YouTube is a separate provider path because the upload-oriented Groq adapter cannot read a YouTube page URL. When Gemini is configured, the backend sends a normalized public YouTube URL directly to Gemini's video input API with the question and recent conversation. The app does not download platform media. Gemini may reject links it cannot access; users can upload a video they have rights to process. Local transcription and dubbing currently require an upload.

## What is on the usage dashboard?

It reports saved LLM calls, provider-reported prompt/completion tokens, request latency, failures, model breakdown, Qwen performance, recent traces, and active local sessions. It does not invent costs or embedding calls. Embeddings are marked as unavailable until a real embedding pipeline is added.

## What protects the user?

Uploads have extension and size checks, and are stored under generated IDs rather than user-supplied paths. The app asks users to confirm processing rights. Video content is evidence, never executable instructions. Credentials stay in environment variables. Public links are not scraped, and the first version has no voice cloning.

## What are the tradeoffs and next steps?

The first version uses simple RQ jobs and PostgreSQL table initialization to keep local setup approachable. Before production, add Alembic migrations, authentication and tenant isolation, retention controls, more robust MIME/content validation, external object storage, retries and cancellation, rate limits, and provider-specific integration tests. Current FFmpeg sampling is intentionally bounded; a production video index could add scene-change detection and vector retrieval. Dubbed output is audio-only; muxing and audio alignment are future work.
