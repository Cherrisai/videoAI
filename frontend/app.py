import os
import requests
from urllib.parse import urlsplit
import streamlit as st

API = os.getenv("API_BASE_URL", "http://api:8000/api").rstrip("/")
PUBLIC_API = os.getenv("API_PUBLIC_URL", "http://localhost:8000/api").rstrip("/")
PUBLIC_ORIGIN = PUBLIC_API.rsplit("/api", 1)[0]
st.set_page_config(page_title="VideoAI", page_icon="V", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root { --cherry:#ed3155; --cherry-dark:#a91439; --cherry-soft:#32131b; --ink:#f4eef0; --muted:#b9aeb2; }
.stApp { background:radial-gradient(ellipse at 12% 0%,#34151e 0,transparent 38%),linear-gradient(160deg,#111013 0%,#171417 55%,#211319 100%); color:var(--ink) !important; }
[data-testid="stMainBlockContainer"] { max-width:1180px !important;margin-inline:auto !important;padding-bottom:8.5rem !important; }
.stApp, .stApp p, .stApp label, .stApp span, .stApp div, .stApp li { color:inherit; }
.stApp [data-testid="stMarkdownContainer"] p, .stApp [data-testid="stMarkdownContainer"] li { color:#eee7e9; }
.stApp h1,.stApp h2,.stApp h3,.stApp h4 { color:#fff7f8 !important; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#30141e,#471827 58%,#2b111a); border-right:1px solid #68253b; }
[data-testid="stSidebar"] * { color:#fff4f6 !important; }
[data-testid="stSidebar"] [data-testid="stFileUploader"] section { background:#ffffff10; border-color:#ffffff35; }
.brand { display:flex; align-items:center; gap:.65rem; font-size:1.45rem; font-weight:800; letter-spacing:-.04em; color:#3b1723; }
.brand-mark { width:2.25rem;height:2.25rem;border-radius:.8rem;display:grid;place-items:center;background:linear-gradient(135deg,#f25b75,#b7163e);color:white;box-shadow:0 7px 18px #ce315235; }
.eyebrow { color:var(--cherry-dark);font-weight:700;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem; }
.hero { padding:1rem 0 .7rem; }
.hero h1 { font-size:2.3rem; letter-spacing:-.055em; margin:.15rem 0 .3rem; color:#fff7f8 !important; }
.hero p { color:#c8b9bf; margin:0; }
[data-testid="stMetric"] { background:#211c20;border:1px solid #443038;border-radius:16px;padding:14px 16px;box-shadow:0 8px 28px #0005; }
[data-testid="stMetricLabel"] { color:#c8b9bf !important; }
[data-testid="stMetricValue"] { color:#fff7f8 !important; }
.stButton>button, .stDownloadButton>button, [data-testid="stLinkButton"] a { border-radius:11px;border:1px solid #54313b;background:#211c20;color:#fff0f3;font-weight:650;transition:all .18s ease; }
.stButton>button:hover, .stDownloadButton>button:hover { border-color:var(--cherry);color:var(--cherry-dark);box-shadow:0 6px 18px #d92f5218; }
.stButton>button { white-space:nowrap; }
.stButton>button[kind="primary"] { background:linear-gradient(135deg,#e34462,#bb1d43);color:white;border:0; }
[data-testid="stChatMessage"] { max-width:960px;width:100%;margin:.7rem auto;border:1px solid #403139;border-radius:18px;background:#211c20;box-shadow:0 8px 26px #0004; }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) { background:#301820;border-color:#713043; }
[data-testid="stChatInput"] { position:fixed!important;z-index:1000;left:max(1rem,calc((100vw - 960px)/2)) !important;right:auto !important;bottom:.75rem;width:min(960px,calc(100vw - 2rem)) !important;max-width:calc(100vw - 2rem) !important;box-sizing:border-box;margin:0 !important;padding:.45rem .6rem;border:1px solid #51303a;border-radius:19px;background:#191619;box-shadow:0 12px 38px #0009; }
[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"][aria-expanded="true"]) [data-testid="stChatInput"] { left:calc(var(--sidebar-width, 21rem) + (100vw - var(--sidebar-width, 21rem) - 960px)/2) !important;width:min(960px,calc(100vw - var(--sidebar-width, 21rem) - 2rem)) !important; }
[data-testid="stChatInput"] > div { border-radius:15px; }
[data-testid="stChatInput"] [data-baseweb="textarea"], [data-testid="stChatInput"] textarea { border:0 !important;outline:0 !important;box-shadow:none !important;background:transparent !important; }
[data-testid="stChatInput"] textarea { color:#fff !important;-webkit-text-fill-color:#fff !important;border-radius:0;background:transparent;caret-color:#ff5472; }
[data-testid="stChatInput"] textarea::placeholder { color:#b7a8ae !important;-webkit-text-fill-color:#b7a8ae !important;opacity:1; }
[data-testid="stChatInput"]:has(textarea:focus) { border-color:var(--cherry);box-shadow:0 0 0 3px #d92f5233,0 12px 38px #0009; }
[data-testid="stChatInput"] button { color:#fff !important;background:#d92f52 !important;border-radius:12px !important; }
[data-testid="stChatInput"] textarea { min-height:3.2rem !important;padding:.85rem 1rem !important;white-space:pre;overflow-x:auto;overflow-y:hidden; }
[data-testid="stSelectbox"] div[data-baseweb="select"] > div { background:#211c20;color:#fff;border-color:#54313b; }
.stTextInput input,.stTextArea textarea { color:#fff !important;background:#211c20 !important; }
.stTextInput input::placeholder,.stTextArea textarea::placeholder { color:#b7a8ae !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color:var(--cherry-dark);border-bottom-color:var(--cherry); }
.signal { display:inline-flex;align-items:center;gap:9px;color:#9b2341;font-weight:650; }
.signal-dots { display:inline-flex;gap:4px; }
.signal-dots i { width:6px;height:6px;border-radius:50%;background:#d92f52;animation:beat 1s infinite ease-in-out; }
.signal-dots i:nth-child(2){animation-delay:.15s}.signal-dots i:nth-child(3){animation-delay:.3s}
@keyframes beat { 0%,70%,100%{transform:translateY(0);opacity:.35}35%{transform:translateY(-5px);opacity:1} }
.callout { background:#261a1f;border:1px solid #693043;border-radius:14px;padding:12px 15px;color:#f4e7eb; }
.footer { margin-top:3rem;padding:1rem 0;border-top:1px solid #403139;color:#b9aeb2;text-align:center;font-size:.82rem; }
@media (max-width: 760px) { [data-testid="stChatInput"] { left:1rem !important;right:auto !important;width:calc(100vw - 2rem) !important;bottom:.5rem; } [data-testid="stMainBlockContainer"] { padding-bottom:7.5rem !important; } }
</style>
""", unsafe_allow_html=True)


def api(method, path, **kwargs):
    try:
        response = requests.request(method, API + path, timeout=kwargs.pop("timeout", 60), **kwargs)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if response.status_code >= 500 and str(detail).strip().lower() == "internal server error":
                detail = "VideoAI could not complete this request. Check the API and worker logs with `docker compose logs --tail=100 api worker`, then verify the selected provider, model name, and API key in Settings."
            st.error(str(detail))
            return None
        return response.json() if response.headers.get("content-type", "").startswith("application/json") else response
    except requests.RequestException:
        st.error("VideoAI API is unreachable. Check that Docker Compose services are running.")
        return None


def looks_like_video_file_url(value: str) -> bool:
    return urlsplit(value.strip()).path.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi"))


def looks_like_youtube_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return parsed.scheme == "https" and host in {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def asks_about_uploaded_video(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in (
        "in the video", "in this video", "this video", "in the clip", "this clip",
        "the scene", "this scene", "the frame", "timestamp", "what happens at", "who is in",
    ))


cfg = api("GET", "/config")
if cfg is None:
    st.stop()
if "user_id" not in st.session_state:
    user = api("POST", "/users")
    if not user:
        st.stop()
    st.session_state.user_id = user["id"]
if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = cfg.get("default_provider") or ""


@st.fragment(run_every="30s")
def live_presence(user_id):
    try:
        response = requests.post(f"{API}/users/{user_id}/heartbeat", timeout=5)
        if response.ok:
            st.markdown("<span style='color:#79e2ae'>●</span> Live session", unsafe_allow_html=True)
    except requests.RequestException:
        pass


with st.sidebar:
    st.markdown("<div class='brand' style='color:#fff4f6'><span class='brand-mark'>V</span>VideoAI</div>", unsafe_allow_html=True)
    st.caption("Video understanding workspace")
    page = st.radio("Navigation", ["Workspace", "Usage dashboard", "Message history", "Settings"], label_visibility="collapsed", key="page_nav")
    st.divider()
    live_presence(st.session_state.user_id)
    if page == "Workspace":
        st.markdown("#### Add a video")
        st.caption("Upload a video file, use a direct video-file URL, or analyze a public YouTube link with Gemini.")
        uploaded = st.file_uploader("MP4, MOV, MKV, WebM, AVI", type=["mp4", "mov", "mkv", "webm", "avi"], label_visibility="collapsed")
        accepted = st.checkbox("I have rights to process this video's picture and audio.")
        if st.button("Upload and analyze", type="primary", disabled=not uploaded or not accepted, use_container_width=True):
            with st.spinner("Uploading video securely…"):
                result = api("POST", "/videos", data={"user_id": st.session_state.user_id}, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}, timeout=180)
            if result:
                st.session_state.video_id = result["id"]
                st.rerun()
        video_link = st.text_input("Video file or web/product link", placeholder="https://media.example.com/video.mp4 or a product page")
        direct_video_url = bool(video_link.strip()) and looks_like_video_file_url(video_link)
        youtube_url = bool(video_link.strip()) and looks_like_youtube_url(video_link)
        if youtube_url:
            if cfg.get("youtube_video_configured"):
                st.caption(f"Public YouTube analysis is enabled with Gemini · {cfg.get('youtube_video_model')}. Private, unlisted, removed, or region-restricted videos may be unavailable.")
            else:
                st.info("YouTube links use Gemini's official video input. Add GEMINI_API_KEY in .env and restart Compose. Your existing Groq setup still works for uploaded videos.")
        elif direct_video_url:
            st.caption("Direct video files only. Platform pages and sign-in links are not fetched.")
        elif video_link.strip():
            st.caption("This looks like a web or product page. Search it online below; it will not be fetched as video.")
        else:
            st.caption("For video import, use a public direct file URL ending in MP4, MOV, MKV, WebM, or AVI.")
        if youtube_url and st.button("Use public YouTube video", disabled=not accepted, use_container_width=True):
            result = api("POST", "/videos/youtube", json={"user_id": st.session_state.user_id, "video_url": video_link.strip()})
            if result:
                st.session_state.video_id = result["id"]
                st.rerun()
        elif st.button("Fetch public video file", disabled=not direct_video_url or not accepted, use_container_width=True):
            with st.spinner("Verifying and fetching the public video file…"):
                result = api("POST", "/videos/from-url", json={"user_id": st.session_state.user_id, "video_url": video_link.strip()}, timeout=240)
            if result:
                st.session_state.video_id = result["id"]
                st.rerun()
        if st.button("Search this link online", disabled=not video_link.strip(), use_container_width=True):
            question = f"Find useful information and relevant links for this page: {video_link.strip()}"
            payload = {"user_id": st.session_state.user_id, "question": question,
                       "language": st.session_state.get("answer_language", "English"),
                       "provider": st.session_state.get("llm_provider") or None}
            if st.session_state.get("search_conversation_id"):
                payload["conversation_id"] = st.session_state.search_conversation_id
            with st.spinner("Searching configured web and product tools…"):
                result = api("POST", "/search", json=payload, timeout=65)
            if result:
                st.session_state.search_conversation_id = result["conversation_id"]
                st.session_state.pending_search_conversation_id = result["conversation_id"]
                st.rerun()
        st.divider()
        st.selectbox("Answer language", cfg["languages"], key="answer_language")
        providers = cfg.get("providers", {})
        if providers:
            provider_ids = list(providers)
            selected = st.session_state.llm_provider if st.session_state.llm_provider in providers else cfg.get("default_provider", provider_ids[0])
            st.selectbox("LLM provider", provider_ids, index=provider_ids.index(selected), format_func=lambda key: providers[key]["label"], key="llm_provider")
        elif not cfg["demo_mode"] and not cfg.get("youtube_video_configured"):
            st.caption("Add a model key in Settings to enable real video chat.")

if cfg["demo_mode"]:
    st.warning("DEMO MODE · Answers and scene descriptions are sample data, not model output.")
def page_header(kicker, title, subtitle):
    st.markdown(f"<div class='hero'><div class='eyebrow'>{kicker}</div><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


@st.fragment(run_every="3s")
def render_processing_status(video_id):
    current = api("GET", f"/videos/{video_id}")
    if not current:
        return
    if current["status"] in ("ready", "failed"):
        st.rerun()
    st.markdown(f"<div class='signal'>Video is {current['status']} <span class='signal-dots'><i></i><i></i><i></i></span></div>", unsafe_allow_html=True)
    st.caption(current["message"])


def render_search_conversation():
    conversations = api("GET", f"/users/{st.session_state.user_id}/search-conversations") or []
    if not conversations:
        st.session_state.pop("search_conversation_id", None)
        st.session_state.pop("search_conversation_selector", None)
        return

    ids = [item["id"] for item in conversations]
    pending_id = st.session_state.pop("pending_search_conversation_id", None)
    if pending_id in ids:
        st.session_state.search_conversation_id = pending_id
        st.session_state.search_conversation_selector = pending_id
    active_id = st.session_state.get("search_conversation_id")
    if active_id not in ids:
        active_id = ids[0]
        st.session_state.search_conversation_id = active_id
    if st.session_state.get("search_conversation_selector") not in ids:
        st.session_state.search_conversation_selector = active_id

    selected_id = st.selectbox(
        "Web search conversation", ids,
        index=ids.index(st.session_state.search_conversation_selector),
        format_func=lambda key: next((item["title"] for item in conversations if item["id"] == key), "Web search"),
        key="search_conversation_selector",
    )
    st.session_state.search_conversation_id = selected_id
    messages = api("GET", f"/search-conversations/{selected_id}/messages",
                   params={"user_id": st.session_state.user_id}) or []
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for citation in message.get("citations", []):
                url = citation.get("url")
                if url:
                    from urllib.parse import urlsplit
                    label = citation.get("title") or urlsplit(url).netloc
                    description = citation.get("description", "")
                    st.markdown(f"[{label}]({url})")
                    if description:
                        st.caption(description)
            if message.get("provider"):
                st.caption(f"{message['provider']} · {message.get('model', '')} · {message.get('latency_ms', 0)} ms")


def run_standalone_search(question: str) -> None:
    with st.spinner("Searching sources and updating your conversation…"):
        payload = {
            "user_id": st.session_state.user_id,
            "question": question,
            "language": st.session_state.get("answer_language", "English"),
            "provider": st.session_state.get("llm_provider") or None,
        }
        if st.session_state.get("search_conversation_id"):
            payload["conversation_id"] = st.session_state.search_conversation_id
        result = api("POST", "/search", json=payload, timeout=65)
    if result:
        st.session_state.search_conversation_id = result["conversation_id"]
        st.session_state.pending_search_conversation_id = result["conversation_id"]
        st.rerun()


def render_workspace():
    page_header("Video workspace", "Ask your video anything.", "A timestamped, evidence-first conversation about the moments that matter.")
    render_search_conversation()
    videos = api("GET", f"/users/{st.session_state.user_id}/videos") or []
    video_id = st.session_state.get("video_id")
    if videos:
        ids = [item["id"] for item in videos]
        if video_id not in ids:
            video_id = ids[0]
            st.session_state.video_id = video_id
        selected_id = st.selectbox("Current video", ids, index=ids.index(video_id), format_func=lambda key: next((v["filename"] for v in videos if v["id"] == key), key))
        if selected_id != video_id:
            st.session_state.video_id = selected_id
            st.rerun()
        video_id = selected_id
    if not video_id:
        prompt = st.chat_input("Search the web, a product page, place, image, or video…")
        if prompt:
            run_standalone_search(prompt)
        return

    info = api("GET", f"/videos/{video_id}")
    if not info:
        return
    top, action = st.columns([5, 1])
    with top:
        st.subheader(info["filename"])
        st.caption(info["message"])
    with action:
        st.metric("Status", info["status"].title())
    if not cfg.get("providers") and not cfg["demo_mode"] and not (info.get("source_type") == "youtube" and cfg.get("youtube_video_configured")):
        st.warning("Real video chat is not enabled yet. Add a Groq, OpenAI, or compatible API key in Settings; upload and frame processing still work.")
    if info["status"] in ("queued", "processing"):
        render_processing_status(video_id)
        st.caption("VideoAI is extracting timestamps and representative frames. This status refreshes automatically.")
        st.button("Check now", on_click=st.rerun)
        prompt = st.chat_input("Search the web or paste a product/video link while processing…")
        if prompt:
            run_standalone_search(prompt)
        return
    if info["status"] == "failed":
        st.error(info["message"])
        if st.button("Retry analysis", type="primary"):
            if api("POST", f"/videos/{video_id}/retry", json={"user_id": st.session_state.user_id}):
                st.rerun()
        prompt = st.chat_input("Search the web, a product page, place, image, or video…")
        if prompt:
            run_standalone_search(prompt)
        return

    source_url = PUBLIC_API + f"/videos/{video_id}/source"
    chat_tab, moments_tab, transcript_tab = st.tabs(["Chat", "Moments", "Transcript & dubbing"])
    with chat_tab:
        history = api("GET", f"/videos/{video_id}/messages") or []
        spacer, clear_col = st.columns([5, 1])
        with clear_col:
            if st.button("Clear chat", help="Delete all messages for this video", disabled=not history):
                api("DELETE", f"/videos/{video_id}/messages", params={"user_id": st.session_state.user_id})
                st.rerun()
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                for citation in message.get("citations", []):
                    if citation.get("url"):
                        label = citation.get("title") or urlsplit(citation["url"]).netloc
                        prefix = "Video moment" if citation.get("timestamp") is not None else "Source"
                        st.markdown(f"{prefix}: [{label}]({citation['url']})")
                    elif citation.get("timestamp") is not None:
                        stamp = int(citation["timestamp"])
                        st.caption(f"Evidence · {stamp//60:02d}:{stamp%60:02d} · {citation.get('description', '')}")
                        if citation.get("image"):
                            st.image(PUBLIC_ORIGIN + citation["image"], width=240)
                if message.get("provider"):
                    st.caption(f"{message['provider']} · {message.get('model', '')} · {message.get('latency_ms', 0)} ms · {message.get('total_tokens', 0)} tokens")
    with moments_tab:
        if info.get("source_type") == "youtube" and info.get("source_url"):
            st.video(info["source_url"])
            st.caption("Video is provided directly to Gemini by URL. VideoAI does not download or store YouTube media.")
        else:
            st.video(source_url)
            st.link_button("Download original video", source_url)
        scenes = info.get("scenes", [])
        if not scenes:
            if info.get("source_type") == "youtube":
                st.info("YouTube frames are inspected by Gemini during chat. Timestamped evidence appears in answers; local frame thumbnails are available for uploaded videos.")
            else:
                st.info("Frame extraction is complete. Add a vision-capable model key to describe what appears in the video.")
        for scene in scenes:
            frame_col, text_col = st.columns([1, 3])
            seconds = int(scene.get("timestamp", 0))
            with frame_col:
                st.image(PUBLIC_ORIGIN + scene.get("image", ""), caption=f"{seconds//60:02d}:{seconds%60:02d}", use_container_width=True)
            with text_col:
                st.markdown(f"**{seconds//60:02d}:{seconds%60:02d}**  {scene.get('description', 'Frame extracted')}")
    with transcript_tab:
        st.caption("ASR, translation, and speech generation are configured independently. Original media remains unchanged.")
        if info.get("source_type") == "youtube":
            st.info("YouTube links are analyzed by URL for video chat. Local transcription, translation, and dubbing need an uploaded video file; upload a video you have rights to process to use these tools.")
        else:
            if cfg["transcription_configured"]:
                st.caption(f"Transcription provider: {cfg.get('transcription_provider', 'configured')} · timestamps and detected speech language are returned when the provider supplies them.")
            if st.button("Transcribe video", disabled=not cfg["transcription_configured"]):
                if api("POST", f"/videos/{video_id}/transcript", json={}, timeout=300):
                    st.rerun()
            if not cfg["transcription_configured"]:
                st.info("Transcription is not configured. Set GROQ_API_KEY to use Groq Whisper, or set WHISPER_API_KEY and WHISPER_BASE_URL for another compatible provider in .env.")
        for segment in info.get("transcript", []):
            start = int(segment.get("start", 0))
            st.markdown(f"**{start//60:02d}:{start%60:02d}** {segment['text']}")
        translations = [key for key in cfg["languages"] if key in cfg["translation_languages"]]
        if info.get("transcript") and translations:
            target = st.selectbox("Translate to", translations)
            if st.button("Translate transcript"):
                if api("POST", f"/videos/{video_id}/translation", json={"target_language": target}, timeout=180):
                    st.rerun()
            for segment in info.get("translations", {}).get(target, []):
                start = int(segment.get("start", 0))
                st.markdown(f"**{start//60:02d}:{start%60:02d} · {target}** {segment['text']}")
        dub_languages = [key for key in translations if key in cfg["tts_languages"]]
        if info.get("transcript"):
            if dub_languages:
                dub_target = st.selectbox("Dub audio language", dub_languages)
                rights = st.checkbox("I have rights to create this dubbed audio; no voice cloning is used.")
                if st.button("Generate dubbed audio", disabled=not rights):
                    result = api("POST", f"/videos/{video_id}/dub", json={"target_language": dub_target, "preserve_original_audio": True}, timeout=300)
                    if result:
                        st.session_state.dub_internal_url = API.rsplit("/api", 1)[0] + result["audio_url"]
                        st.rerun()
            else:
                st.caption("Dubbing requires a configured translation language and matching TTS language.")
        dub_url = st.session_state.get("dub_internal_url")
        if dub_url:
            response = requests.get(dub_url, timeout=120)
            if response.ok:
                st.audio(response.content, format="audio/mp3")
                st.download_button("Download dubbed audio", response.content, file_name="videoai-dub.mp3", mime="audio/mpeg")

    prompt = st.chat_input("Ask about the people, objects, actions, or moments in this video…")
    if prompt:
        if st.session_state.get("search_conversation_id") and not asks_about_uploaded_video(prompt):
            run_standalone_search(prompt)
        else:
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                response_slot = st.empty()
                response_slot.markdown("<div class='signal'>Checking video evidence and relevant sources <span class='signal-dots'><i></i><i></i><i></i></span></div>", unsafe_allow_html=True)
                result = api("POST", f"/videos/{video_id}/chat", json={
                    "question": prompt,
                    "language": st.session_state.answer_language,
                    "provider": st.session_state.llm_provider or None,
                }, timeout=600 if info.get("source_type") == "youtube" else 65)
                if result:
                    response_slot.markdown(result["answer"])
                    for index, citation in enumerate(result.get("citations", [])[:8], start=1):
                        if citation.get("url"):
                            st.markdown(f"[{citation.get('title') or citation.get('source', 'Search result')} · result {index}]({citation['url']})")
                    if result.get("demo"):
                        st.caption("Demo response · sample data")
                else:
                    response_slot.error("This request did not return an answer. Your question remains in the conversation; check the message above and try again when the provider is available.")
            if result:
                st.rerun()


@st.fragment(run_every="10s")
def render_dashboard():
    page_header("Observability", "Usage dashboard", "Live provider traces and performance based on real completed requests.")
    videos = api("GET", f"/users/{st.session_state.user_id}/videos") or []
    latest_video_id = videos[0]["id"] if videos else None
    video_options = (["Latest video", "All videos"] + [video["id"] for video in videos[1:]]) if videos else ["All videos"]
    selected_video = st.selectbox("Metrics scope", video_options,
        format_func=lambda key: ("Latest video · " + videos[0]["filename"] if key == "Latest video" else
            "All videos" if key == "All videos" else next((v["filename"] for v in videos if v["id"] == key), key)),
        key="dashboard_video_scope")
    params = {"user_id": st.session_state.user_id}
    selected_video_id = latest_video_id if selected_video == "Latest video" else selected_video
    if selected_video_id != "All videos":
        params["video_id"] = selected_video_id
    data = api("GET", "/dashboard/metrics", params=params)
    if not data:
        return
    metric_cols = st.columns(5)
    for col, label, value in zip(metric_cols, ["LLM calls", "Tokens", "Avg latency", "Videos", "Messages"],
                                 [data["llm_calls"], f"{data['tokens']:,}", f"{data['average_latency_ms']} ms", data["videos"], data["messages"]]):
        col.metric(label, value)
    latency_col, token_col = st.columns(2)
    latency_col.metric("P95 latency", f"{data['p95_latency_ms']} ms", help="95th percentile of recorded successful LLM request latency.")
    latency_col.metric("Failed calls", data["failed_calls"])
    token_col.metric("Prompt / completion", f"{data['prompt_tokens']:,} / {data['completion_tokens']:,}")
    st.subheader("Qwen model performance")
    qwen = data["qwen"]
    q_cols = st.columns(4)
    q_cols[0].metric("Qwen calls", qwen["calls"])
    q_cols[1].metric("Average latency", f"{qwen['avg_latency_ms']} ms")
    q_cols[2].metric("Tokens", f"{qwen['tokens']:,}")
    q_cols[3].metric("Failures", qwen["failures"])
    if not qwen["calls"]:
        st.caption("No Qwen requests have been recorded yet. Configure Groq and select its Qwen vision model in Settings.")
    chart_col_a, chart_col_b = st.columns(2)
    with chart_col_a:
        st.subheader("Calls by hour")
        if data["timeseries"]:
            st.bar_chart(data["timeseries"], x="hour", y="calls", color="#d92f52")
        else:
            st.caption("Usage charts will populate after configured provider calls.")
    with chart_col_b:
        st.subheader("Latency by hour")
        if data["timeseries"]:
            st.line_chart(data["timeseries"], x="hour", y="avg_latency_ms", color="#b71943")
        else:
            st.caption("No measured latency yet.")
    st.subheader("Live sessions")
    st.metric("Active anonymous browser sessions · last 5 minutes", len(data["active_users"]))
    if data["active_users"]:
        st.dataframe(data["active_users"], use_container_width=True, hide_index=True)
    st.subheader("Request traces")
    if data["traces"]:
        st.dataframe(data["traces"], use_container_width=True, hide_index=True)
    else:
        st.caption("No provider calls recorded. Add an API key in Settings to begin collecting traces.")


def open_history_video(video_id: str) -> None:
    st.session_state.video_id = video_id
    st.session_state.page_nav = "Workspace"


def render_history():
    page_header("Library", "Message history", "Review past video conversations and remove messages when you choose.")
    videos = api("GET", f"/users/{st.session_state.user_id}/videos") or []
    if not videos:
        st.info("Your video conversations will appear here after your first upload.")
        return
    for video in videos:
        with st.expander(f"{video['filename']} · {video['status']} · {video['message_count']} messages"):
            st.button("Open in workspace", key=f"open-{video['id']}", on_click=open_history_video, args=(video["id"],))
            messages = api("GET", f"/videos/{video['id']}/messages") or []
            if st.button("Delete this conversation", key=f"clear-{video['id']}", disabled=not messages):
                api("DELETE", f"/videos/{video['id']}/messages", params={"user_id": st.session_state.user_id})
                st.rerun()
            for message in messages:
                label = "You" if message["role"] == "user" else "VideoAI"
                st.markdown(f"**{label}:** {message['content']}")
                if st.button("Delete message", key=f"delete-{message['id']}"):
                    api("DELETE", f"/videos/{video['id']}/messages/{message['id']}", params={"user_id": st.session_state.user_id})
                    st.rerun()


def render_settings():
    page_header("Preferences", "Settings", "Choose the provider for this browser session. API keys stay in your environment file.")
    st.subheader("External lookups")
    if not cfg.get("mcp_tools"):
        st.info("External search is unavailable. Add a provider key such as BRAVE_API_KEY in .env or configure a trusted MCP server, then restart Compose.")
    else:
        connected_servers = sorted({tool.get("server", "MCP server") for tool in cfg["mcp_tools"]})
        st.success("MCP connected · " + ", ".join(connected_servers))
        st.caption("Ask explicitly, for example: ‘Search the web for …’. Product requests use web results as likely matches; place availability depends on your Brave plan.")

    providers = cfg.get("providers", {})
    if providers:
        options = list(providers)
        current = st.session_state.llm_provider if st.session_state.llm_provider in providers else options[0]
        selected = st.selectbox("Video understanding and chat provider", options, index=options.index(current),
                                format_func=lambda key: providers[key]["label"])
        st.session_state.llm_provider = selected
        details = providers[selected]
        st.markdown(f"<div class='callout'><b>Active provider:</b> {details['label']}<br><b>Vision model:</b> {details['vision_model']}<br><b>Chat model:</b> {details['chat_model']}<br><b>Endpoint:</b> {details['base_url']}</div>", unsafe_allow_html=True)
        if selected == "groq":
            st.caption("Groq is configured with a multimodal Qwen model for frame analysis and chat. Provider pricing and available models can change; check the provider console before large workloads.")
    elif not cfg.get("youtube_video_configured"):
        st.warning("No LLM API key is configured. Add GROQ_API_KEY, OPENAI_API_KEY, or custom provider values to .env, then restart Compose.")
        st.markdown("[Create a Groq API key](https://console.groq.com/keys)")
        st.code("cp .env.example .env\n# Add GROQ_API_KEY=...\nAPI_HOST_PORT=18000 STREAMLIT_HOST_PORT=18501 docker compose up --build -d", language="sh")
    else:
        st.info("Gemini is configured for public YouTube links. Add Groq, OpenAI, or another compatible provider to enable uploaded-file frame analysis.")
        st.markdown(f"**YouTube model:** `{cfg.get('youtube_video_model', 'configured')}` · Set `GEMINI_API_KEY` in `.env` to change credentials.")
    with st.expander("Provider setup"):
        st.markdown("""
**Recommended: Groq** — set `GROQ_API_KEY`. The default vision/chat model is `qwen/qwen3.8-27b`.

**OpenAI** — set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `VISION_MODEL`, and `CHAT_MODEL`.

**Other OpenAI-compatible provider** — set `CUSTOM_API_KEY`, `CUSTOM_BASE_URL`, `CUSTOM_VISION_MODEL`, and `CUSTOM_CHAT_MODEL`.

**Public YouTube links** — set `GEMINI_API_KEY` and optionally `GEMINI_VIDEO_MODEL` (default `gemini-3.8-flash`). YouTube URL analysis is separate from Groq and supports only videos Gemini can access. Upload a file for private/restricted videos, transcription, or dubbing.

Restart the API and worker after changing `.env`. Keys are never stored in chat history or browser state.
        """)
    st.subheader("Privacy and live tracking")
    st.caption("VideoAI records session activity time and model request metadata (provider, model, latency, token counts, and status) for this local deployment. Prompt and video contents are not included in usage traces. This app has no account authentication; keep it on a trusted machine/network.")
    st.markdown("<div class='footer'>© Saivignesh @ 2026 · VideoAI</div>", unsafe_allow_html=True)


if page == "Workspace":
    render_workspace()
elif page == "Usage dashboard":
    render_dashboard()
elif page == "Message history":
    render_history()
else:
    render_settings()
