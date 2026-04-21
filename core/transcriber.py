"""
Audio transcription using Gemini multimodal models.
"""

import json
import mimetypes
import os

from core.ai_handler import AIHandler
from core.ai_response_utils import get_response_payload, parse_json_array, parse_json_object
from core.settings_manager import settings

TRANSCRIPTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
            },
        }
    },
    "required": ["segments"],
}


def transcribe(audio_path: str, log_cb=None, model_override: str | None = None) -> tuple[list[dict], float]:
    def _log(msg: str):
        print(f"[Transcriber] {msg}")
        if log_cb:
            log_cb(msg)

    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError("File audio tidak ditemukan.")

    AIHandler.ensure_ready()
    model_name = str(model_override or settings.get_model_for_task("transcribe") or "").strip()
    if not model_name:
        model_name = "gemini-2.5-flash"
    client = AIHandler.get_client()

    _log(f"Upload audio ke Gemini: {os.path.basename(audio_path)}")

    prompt = """Tolong transkripsi audio ini ke dalam Bahasa Indonesia.
Aturan penting:
- Setiap objek adalah satu segmen kalimat/frasa yang natural
- "start" dan "end" adalah timestamp dalam DETIK (format float)
- "text" adalah teks yang diucapkan, bersih tanpa tanda baca berlebihan
- Jika audio berbahasa campur, tetap tulis apa adanya
- Pastikan coverage timestamp mencakup seluruh durasi audio
- Jawab HANYA dengan JSON valid"""

    try:
        from google.genai import types

        mime_type, _ = mimetypes.guess_type(audio_path)
        if not mime_type:
            mime_type = "audio/mpeg"
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)
        model_input = [audio_part, prompt]
        _log("Audio berhasil disiapkan untuk model")
    except Exception as e:
        raise RuntimeError(f"Gagal menyiapkan audio: {e}") from e

    _log(f"Mengirim ke {model_name} untuk transkripsi...")

    last_error = None
    raw_text = ""
    parsed_payload = None
    raw_segments = []
    for attempt in range(1, 4):
        try:
            config = AIHandler.prepare_config(
                temperature=0.1,
                max_tokens=12000,
                mime_type="application/json",
                schema=TRANSCRIPTION_RESPONSE_SCHEMA,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=model_input,
                config=config,
            )
            raw_text, parsed_payload = get_response_payload(response)
            raw_segments = _parse_transcription_segments(raw_text, parsed_payload)
            break
        except Exception as e:
            last_error = e
            _log(f"Attempt {attempt} gagal: {e}")
    else:
        snippet = raw_text[:600].replace("\n", "\\n") if raw_text else "-"
        raise RuntimeError(
            "Gemini gagal mengembalikan transkripsi JSON yang valid.\n"
            f"Error terakhir: {last_error}\n"
            f"Snippet output: {snippet}"
        ) from last_error

    segments = []
    for item in raw_segments:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = _safe_float(item.get("start", 0), 0.0)
        end = _safe_float(item.get("end", start + 1), start + 1.0)
        if end <= start:
            end = start + 1.0
        segments.append({"start": start, "end": end, "text": text})
        _log(f"  [{start:.1f}s - {end:.1f}s] {text[:60]}...")

    segments.sort(key=lambda item: item["start"])
    if not segments:
        raise RuntimeError("Transkripsi kosong - tidak ada teks terdeteksi dalam audio.")

    total_duration = segments[-1]["end"]
    _log(f"Selesai - {len(segments)} segmen, total {total_duration:.1f}s")
    return segments, total_duration


def _parse_transcription_segments(raw_text: str, parsed_payload=None) -> list[dict]:
    if isinstance(parsed_payload, dict):
        segments = parsed_payload.get("segments", [])
        if isinstance(segments, list):
            return segments
    if isinstance(parsed_payload, list):
        return parsed_payload
    try:
        data = parse_json_object(raw_text)
        segments = data.get("segments", [])
        if isinstance(segments, list):
            return segments
    except json.JSONDecodeError:
        pass
    data = parse_json_array(raw_text)
    return data if isinstance(data, list) else []


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
