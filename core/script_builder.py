import re

from core.ai_handler import AIHandler
from core.ai_response_utils import get_response_payload
from core.settings_manager import settings
from core.research_provider import ResearchProvider


def normalize_script_text(text: str) -> str:
    paragraphs = []
    for raw_line in str(text or "").replace("\r\n", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs).strip()


def build_script_from_manual_text(title: str, text: str) -> dict:
    script_text = normalize_script_text(text)
    if not script_text:
        raise ValueError("Teks script manual masih kosong.")
    return {
        "title": str(title or "").strip(),
        "script_text": script_text,
        "source_type": "manual",
        "version": 1,
    }


def build_script_from_title(title: str, angle: str = "", log_cb=None) -> dict:
    def _log(message: str):
        if log_cb:
            log_cb(message)

    clean_title = str(title or "").strip()
    clean_angle = str(angle or "").strip()
    if not clean_title:
        raise ValueError("Judul/topik untuk full auto masih kosong.")

    try:
        query = clean_title
        if clean_angle:
            query += f" (Fokus pada: {clean_angle})"
        
        research_pack = ResearchProvider.perform_research(query, log_cb=_log)
    except Exception as exc:
        _log(f"Riset gagal, menggunakan fallback. Detail: {exc}")
        research_pack = {
            "research_text": "Informasi spesifik tidak ditemukan, gunakan pengetahuan umum.",
            "source": "fallback"
        }

    return build_script_from_research(clean_title, research_pack, clean_angle, log_cb=log_cb)

def build_script_from_research(title: str, research_pack: dict, angle: str = "", log_cb=None) -> dict:
    def _log(message: str):
        if log_cb:
            log_cb(message)

    clean_title = str(title or "").strip()
    clean_angle = str(angle or "").strip()
    research_text = research_pack.get("research_text", "")
    
    prompt = (
        "Tulis narasi video pendek berbahasa Indonesia yang natural, jelas, dan siap dibacakan voice over.\n"
        "Gunakan informasi berikut sebagai bahan dasar naskah:\n"
        f"--- BAHAN RISET ---\n{research_text}\n-----------------\n\n"
        "Aturan:\n"
        "- Jangan pakai bullet point\n"
        "- Tulis sebagai narasi utuh\n"
        "- Panjang sekitar 8 sampai 14 kalimat\n"
        "- Hindari pembuka yang terlalu formal\n"
        "- Akhiri dengan penutup singkat\n"
        f"- Judul/topik: {clean_title}\n"
    )
    if clean_angle:
        prompt += f"- Angle/tujuan konten: {clean_angle}\n"
    prompt += "\nKembalikan hanya teks narasi final."

    try:
        AIHandler.ensure_ready()
        client = AIHandler.get_client()
        model_name = settings.get("gemini_model_text", "gemini-2.5-flash")
        _log(f"Menyusun draft script dari hasil riset dengan {model_name}...")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=AIHandler.prepare_config(temperature=0.7, max_tokens=2500),
        )
        raw_text, _ = get_response_payload(response)
        script_text = normalize_script_text(raw_text)
        if script_text:
            return {
                "title": clean_title,
                "script_text": script_text,
                "source_type": "research_generated",
                "research_pack": research_pack,
                "version": 1,
            }
    except Exception as exc:
        _log(f"Draft AI gagal, pakai template lokal. Detail: {exc}")

    fallback = normalize_script_text(
        "\n".join(
            [
                f"Pada video ini kita akan membahas {clean_title}.",
                f"Fokus utamanya adalah {clean_angle}." if clean_angle else "",
                "Kita mulai dari gambaran singkat agar topik ini mudah dipahami.",
                "Setelah itu kita masuk ke poin-poin penting yang paling relevan untuk penonton.",
                "Di bagian akhir, kita tarik kesimpulan singkat yang mudah diingat.",
            ]
        )
    )
    return {
        "title": clean_title,
        "script_text": fallback,
        "source_type": "title_template",
        "research_pack": research_pack,
        "version": 1,
    }
