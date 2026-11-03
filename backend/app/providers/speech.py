import httpx
from app.core.config import get_settings
from app.core.errors import ProviderUnavailable


SUPPORTED = ["English", "Tamil", "Hindi", "Kannada", "Telugu"]


class SpeechProvider:
    def __init__(self):
        self.settings = get_settings()

    async def transcribe(self, path: str) -> list[dict]:
        s = self.settings
        if s.whisper_api_key and s.whisper_base_url:
            api_key, endpoint, model = s.whisper_api_key, s.whisper_base_url, s.whisper_model
        elif s.groq_api_key:
            api_key = s.groq_api_key
            endpoint = s.groq_base_url.rstrip("/") + "/audio/transcriptions"
            model = "whisper-large-v3-turbo"
        else:
            raise ProviderUnavailable("Transcription is unavailable. Configure GROQ_API_KEY to use Groq Whisper, or set WHISPER_API_KEY and WHISPER_BASE_URL for another compatible endpoint.")
        async with httpx.AsyncClient(timeout=300) as client:
            with open(path, "rb") as audio:
                response = await client.post(endpoint, headers={"Authorization": f"Bearer {api_key}"}, data={"model": model, "response_format": "verbose_json", "timestamp_granularities[]": "segment"}, files={"file": ("audio.mp3", audio, "audio/mpeg")})
            response.raise_for_status()
            payload = response.json()
        return [{"start": seg["start"], "end": seg["end"], "text": seg["text"], "language": payload.get("language")} for seg in payload.get("segments", [])]


class TranslationProvider:
    async def translate(self, transcript: list[dict], target: str) -> list[dict]:
        s = get_settings()
        languages = {x.strip() for x in s.translation_languages.split(",") if x.strip()}
        if target not in languages or not s.translation_api_key or not s.translation_base_url:
            raise ProviderUnavailable(f"Translation to {target} is not configured. Set TRANSLATION_API_KEY, TRANSLATION_BASE_URL, TRANSLATION_MODEL, and explicitly include {target} in TRANSLATION_LANGUAGES.")
        # OpenAI-compatible chat completion; timing metadata is kept intact per segment.
        text = "\n".join(f"{i}\t{seg['text']}" for i, seg in enumerate(transcript))
        async with httpx.AsyncClient(timeout=180) as client:
            res = await client.post(s.translation_base_url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {s.translation_api_key}"}, json={"model": s.translation_model, "messages": [{"role": "system", "content": f"Translate each numbered line into {target}. Return only numbered translated lines."}, {"role": "user", "content": text}]})
            res.raise_for_status()
        translated = res.json()["choices"][0]["message"]["content"].splitlines()
        texts = {int(row.split("\t", 1)[0]): row.split("\t", 1)[1] for row in translated if "\t" in row and row.split("\t", 1)[0].isdigit()}
        return [{**seg, "text": texts.get(i, seg["text"]), "translated": True, "target_language": target} for i, seg in enumerate(transcript)]


class TTSProvider:
    async def synthesize(self, transcript: list[dict], target: str, output_path: str) -> str:
        s = get_settings()
        languages = {x.strip() for x in s.tts_languages.split(",") if x.strip()}
        if target not in languages or not s.tts_api_key or not s.tts_base_url:
            raise ProviderUnavailable(f"Dub audio for {target} is unavailable. Configure TTS_API_KEY, TTS_BASE_URL, TTS_MODEL, and explicitly include {target} in TTS_LANGUAGES.")
        text = " ".join(x["text"] for x in transcript)
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post(s.tts_base_url, headers={"Authorization": f"Bearer {s.tts_api_key}"}, json={"model": s.tts_model, "input": text, "language": target, "response_format": "mp3"})
            res.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(res.content)
        return output_path
