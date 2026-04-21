import re
import wave

from google.genai import types

from core.ai_handler import AIHandler
from core.settings_manager import settings

AVAILABLE_TTS_VOICES = [
    "Kore",
    "Puck",
    "Charon",
    "Fenrir",
    "Leda",
    "Aoede",
    "Orus",
    "Zephyr",
]

_PCM_RATE = 24000
_PCM_CHANNELS = 1
_PCM_WIDTH = 2


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _split_text_chunks(text: str, max_chars: int = 1400) -> list[str]:
    cleaned = str(text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    chunks = []
    current = ""

    def _commit():
        nonlocal current
        normalized = current.strip()
        if normalized:
            chunks.append(normalized)
        current = ""

    for paragraph in paragraphs:
        paragraph = _normalize_text(paragraph)
        if len(paragraph) > max_chars:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        else:
            sentences = [paragraph]

        for sentence in sentences:
            sentence = _normalize_text(sentence)
            if not sentence:
                continue
            tentative = f"{current} {sentence}".strip() if current else sentence
            if len(tentative) <= max_chars:
                current = tentative
                continue
            _commit()
            if len(sentence) <= max_chars:
                current = sentence
                continue
            start = 0
            while start < len(sentence):
                piece = sentence[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                start += max_chars
    _commit()
    return chunks


def _write_wave_file(path: str, pcm: bytes):
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(_PCM_CHANNELS)
        wav_file.setsampwidth(_PCM_WIDTH)
        wav_file.setframerate(_PCM_RATE)
        wav_file.writeframes(pcm)


def _extract_audio_bytes(response) -> bytes:
    try:
        return response.candidates[0].content.parts[0].inline_data.data or b""
    except Exception:
        return b""


class GeminiTTSProvider:
    provider_name = "gemini"

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str = "",
        model_name: str | None = None,
        log_cb=None,
    ) -> dict:
        def _log(message: str):
            if log_cb:
                log_cb(message)

        script_text = str(text or "").strip()
        if not script_text:
            raise ValueError("Script final kosong, tidak bisa membuat TTS.")

        AIHandler.ensure_ready()
        client = AIHandler.get_client()
        active_model = str(model_name or settings.get_model_for_task("tts") or "").strip()
        if not active_model:
            active_model = "gemini-3.1-flash-tts-preview"
        active_voice = str(voice_name or settings.get("tts_voice_name", "Kore") or "Kore").strip()

        chunks = _split_text_chunks(script_text)
        if not chunks:
            raise ValueError("Script final kosong setelah dibersihkan.")

        pcm_parts = []
        silence = b"\x00\x00" * int(_PCM_RATE * 0.18)
        for index, chunk in enumerate(chunks, start=1):
            _log(f"TTS chunk {index}/{len(chunks)} dengan suara {active_voice}...")
            response = client.models.generate_content(
                model=active_model,
                contents=chunk,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=active_voice,
                            )
                        )
                    ),
                ),
            )
            audio_bytes = _extract_audio_bytes(response)
            if not audio_bytes:
                raise RuntimeError("Model TTS tidak mengembalikan audio PCM yang valid.")
            pcm_parts.append(audio_bytes)
            if index < len(chunks):
                pcm_parts.append(silence)

        merged_pcm = b"".join(pcm_parts)
        _write_wave_file(output_path, merged_pcm)
        return {
            "audio_path": output_path,
            "provider": self.provider_name,
            "voice_id": active_voice,
            "model_name": active_model,
            "chunks": len(chunks),
            "sample_rate": _PCM_RATE,
        }
