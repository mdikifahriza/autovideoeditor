# ─────────────────────────────────────────────
#  core/vision_validator.py  —  Gemini Vision B-roll Validator
# ─────────────────────────────────────────────
"""
Kirim thumbnail kandidat B-roll ke Gemini Vision.
Gemini pilih yang paling relevan dengan konteks transkrip segmen.
"""

import os
import re

from core.ai_response_utils import get_response_payload


def _extract_index(answer: str, max_index: int) -> int:
    match = re.search(r"\d+", answer or "")
    idx = int(match.group()) if match else 0
    return max(0, min(idx, max_index))

def validate_and_choose(segment: dict, log_cb=None) -> dict:
    """
    Untuk satu segmen, kirim thumbnail kandidat ke Gemini Vision.
    Gemini return index kandidat terbaik.
    Update segment["broll_chosen"] dengan pilihan terbaik.
    """
    from core.ai_handler import AIHandler
    from core.settings_manager import settings
    from google.genai import types

    model_name = settings.get_model_for_task("vision")

    def _log(msg):
        print(f"[Vision] {msg}")
        if log_cb:
            log_cb(msg)

    candidates = segment.get("broll_candidates", [])
    valid = [c for c in candidates if c.get("thumbnail_path") and
             os.path.exists(c["thumbnail_path"])]

    if not valid:
        _log(f"Seg {segment['id']}: tidak ada thumbnail valid, skip")
        return segment

    if len(valid) == 1:
        segment["broll_chosen"] = valid[0]
        return segment

    try:
        AIHandler.ensure_ready()
        client = AIHandler.get_client()
        
        transcript = segment.get("transcript", "")
        keywords   = ", ".join(segment.get("broll_keywords", []))

        prompt = (
            f"Kamu adalah editor video profesional.\n"
            f"Konteks voiceover: \"{transcript}\"\n"
            f"Keyword B-roll: {keywords}\n\n"
            f"Di bawah ini ada {len(valid)} thumbnail kandidat video B-roll (index 0 sampai {len(valid)-1}).\n"
            f"Pilih SATU thumbnail yang paling relevan secara visual.\n"
            f"Jawab HANYA dengan angka index saja (contoh: 2). Tanpa penjelasan apapun."
        )
        
        parts = [prompt]
        for i, c in enumerate(valid):
            try:
                with open(c["thumbnail_path"], "rb") as f:
                    img_bytes = f.read()
                
                # Gunakan types.Part.from_bytes yang kompatibel dengan kedua provider
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                parts.append(f"[Index {i}]")
            except Exception as e:
                _log(f"Error baca thumbnail {c['thumbnail_path']}: {e}")

        image_count = sum(1 for part in parts if hasattr(part, "inline_data"))
        if image_count == 0:
            _log(f"Seg {segment['id']}: semua thumbnail gagal dibaca, pakai kandidat pertama")
            segment["broll_chosen"] = valid[0]
            return segment

        config = AIHandler.prepare_config(
            temperature=0.1,
            max_tokens=10
        )
        
        response = client.models.generate_content(
            model=model_name,
            contents=parts,
            config=config
        )
        answer, _ = get_response_payload(response)
        idx = _extract_index(answer, len(valid) - 1)

        _log(f"Seg {segment['id']}: Gemini pilih index {idx} dari {len(valid)} kandidat")
        segment["broll_chosen"] = valid[idx]

    except Exception as e:
        _log(f"Seg {segment['id']}: validasi gagal ({e}), pakai kandidat pertama")
        segment["broll_chosen"] = valid[0]

    return segment


def validate_all_segments(plan: dict, progress_cb=None, log_cb=None) -> dict:
    """Jalankan validasi Gemini Vision untuk semua segmen."""
    segments = plan["segments"]
    total = len(segments)
    
    for i, seg in enumerate(segments):
        if progress_cb:
            progress_cb(i, total, f"Validasi segmen {i+1}/{max(total, 1)}...")
        validate_and_choose(seg, log_cb=log_cb)
        
    if progress_cb:
        progress_cb(total, total, "Validasi selesai")
    return plan
