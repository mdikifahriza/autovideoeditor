import json
import math

from config import (
    AVAILABLE_EFFECTS,
    AVAILABLE_GRADES,
    AVAILABLE_TRANSITIONS,
    SEG_IDEAL,
    SEG_MAX,
    SEG_MIN,
)
from core.ai_handler import AIHandler
from core.ai_response_utils import get_response_payload, parse_json_object
from core.settings_manager import settings

PLANNER_BATCH_SCHEMA = {
    "type": "object",
    "propertyOrdering": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "propertyOrdering": ["id", "k", "tin", "tout", "fx", "grade", "emp"],
                "properties": {
                    "id": {"type": "integer"},
                    "k": {"type": "array", "items": {"type": "string"}},
                    "tin": {"type": "string"},
                    "tout": {"type": "string"},
                    "fx": {"type": "string"},
                    "grade": {"type": "string"},
                    "emp": {"type": "string", "nullable": True},
                },
                "required": ["id", "k", "tin", "tout", "fx", "grade", "emp"],
            },
        }
    },
    "required": ["items"],
}

PLANNER_SYSTEM_PROMPT = """
Kamu adalah B-Roll Editor.
Tugas: memecah input teks menjadi array JSON.
Setiap item mewakili satu segmen dengan metadata kreatif.

Contoh output:
{
  "items": [
    {
      "id": 0,
      "k": ["nature", "forest"],
      "emp": null
    }
  ]
}

Aturan:
- k harus array string keyword pencarian b-roll (satu atau dua kata).
- emp berisi teks emphasis singkat dalam bahasa Indonesia atau null jika tidak perlu.
- Jangan ulang transcript.
- Jaga output sependek mungkin.
""".strip()


def generate_edit_plan(raw_segments: list[dict], total_duration: float, log_cb=None) -> dict:
    """Build a compact edit plan with local segmentation and batched Gemini enrichment."""

    def _log(msg: str):
        print(f"[Planner] {msg}")
        if log_cb:
            log_cb(msg)

    AIHandler.ensure_ready()
    model_name = settings.get_model_for_task("planner")
    client = AIHandler.get_client()

    base_segments = _build_local_visual_segments(raw_segments, total_duration)
    if not base_segments:
        _log("Segmentasi lokal kosong, pakai fallback per segmen transkrip.")
        base_segments = _fallback_segments_from_transcript(raw_segments, total_duration)

    _log(
        f"Segmentasi lokal selesai: {len(base_segments)} blok. "
        f"Mengisi metadata kreatif per batch dengan {model_name}..."
    )

    enriched_segments, used_fallback = _enrich_segments_in_batches(
        client,
        model_name,
        base_segments,
        log_cb=_log,
    )
    enriched_segments = _cap_emphasis_segments(enriched_segments)

    plan = {
        "segments": enriched_segments,
        "project_settings": {
            "subtitle_enabled": False,
            "subtitle_style": "clean",
            "intro_video": None,
            "outro_video": None,
            "floating_text_enabled": False,
            "floating_text_font": "Segoe UI",
            "floating_text_size": 58,
            "floating_text_animation": "slide_up",
            "floating_text_position": "upper_third",
        },
    }
    if used_fallback:
        plan["used_fallback_plan"] = True
    _log(f"Selesai - {len(enriched_segments)} segmen direncanakan")
    return plan


def _build_local_visual_segments(raw_segments: list[dict], total_duration: float) -> list[dict]:
    import math
    cleaned = []
    for raw in raw_segments:
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        start = _safe_float(raw.get("start", 0), 0.0)
        end = _safe_float(raw.get("end", start + 1.0), start + 1.0)
        if end <= start:
            end = start + 1.0
            
        duration = end - start
        if duration > SEG_MAX:
            pieces = math.ceil(duration / SEG_MAX)
            words = text.split()
            words_per_piece = math.ceil(len(words) / pieces) if pieces > 0 and len(words) > 0 else 1
            piece_dur = duration / pieces
            for i in range(pieces):
                p_start = start + i * piece_dur
                p_end = start + (i + 1) * piece_dur if i < pieces - 1 else end
                p_text = " ".join(words[i * words_per_piece : (i + 1) * words_per_piece])
                cleaned.append({"start": p_start, "end": p_end, "text": p_text})
        else:
            cleaned.append({"start": start, "end": end, "text": text})

    if not cleaned:
        return []

    groups = []
    current_group = []

    for index, item in enumerate(cleaned):
        current_group.append(item)
        group_start = current_group[0]["start"]
        group_end = current_group[-1]["end"]
        duration = group_end - group_start
        next_item = cleaned[index + 1] if index + 1 < len(cleaned) else None
        next_would_exceed = bool(
            next_item and (float(next_item["end"]) - float(group_start)) > float(SEG_MAX)
        )
        ready_to_close = duration >= SEG_MIN and (
            _looks_like_sentence_break(item["text"]) or duration >= SEG_IDEAL or next_would_exceed
        )
        must_close = duration >= SEG_MAX or next_item is None

        if ready_to_close or must_close:
            groups.append(current_group)
            current_group = []

    if current_group:
        groups.append(current_group)

    groups = _merge_short_groups(groups)
    segments_out = []
    for idx, group in enumerate(groups):
        segments_out.append(_group_to_segment(group, idx, total_duration))
        
    if segments_out:
        last_end = float(segments_out[-1]["end"])
        while last_end < total_duration:
            gap = total_duration - last_end
            filler_dur = min(gap, SEG_MAX)
            new_end = last_end + filler_dur
            idx = len(segments_out)
            segments_out.append({
                "id": idx,
                "start": last_end,
                "end": new_end,
                "render_duration": max(1.0, filler_dur),
                "transcript": "",
                "subtitle_text": "",
                "broll_keywords": ["nature"],
                "broll_chosen": None,
                "broll_candidates": [],
                "transition_in": "cut",
                "transition_out": "cut",
                "effect": "static",
                "color_grade": "neutral",
                "emphasis_text": None,
                "floating_text_mode": "inherit",
                "confirmed": False,
            })
            last_end = new_end
            
    return segments_out


def _merge_short_groups(groups: list[list[dict]]) -> list[list[dict]]:
    if not groups:
        return []

    merged = [groups[0]]
    for group in groups[1:]:
        current_duration = float(group[-1]["end"]) - float(group[0]["start"])
        prev_group = merged[-1]
        prev_duration = float(prev_group[-1]["end"]) - float(prev_group[0]["start"])
        if current_duration < SEG_MIN and (prev_duration + current_duration) <= (SEG_MAX + 1.5):
            merged[-1] = prev_group + group
        else:
            merged.append(group)
    return merged


def _group_to_segment(group: list[dict], idx: int, total_duration: float) -> dict:
    start = max(0.0, _safe_float(group[0].get("start", 0.0), 0.0))
    end = min(float(total_duration), _safe_float(group[-1].get("end", total_duration), total_duration))
    if end <= start:
        end = min(float(total_duration), start + max(1.0, float(SEG_IDEAL)))
    transcript = " ".join(str(item.get("text", "")).strip() for item in group).strip()

    return {
        "id": idx,
        "start": start,
        "end": end,
        "render_duration": max(1.0, end - start),
        "transcript": transcript,
        "subtitle_text": transcript,
        "broll_keywords": ["nature"],
        "broll_chosen": None,
        "broll_candidates": [],
        "transition_in": "cut",
        "transition_out": "cut",
        "effect": "static",
        "color_grade": "neutral",
        "emphasis_text": None,
        "floating_text_mode": "inherit",
        "confirmed": False,
    }


def _enrich_segments_in_batches(client, model_name: str, segments: list[dict], log_cb=None) -> tuple[list[dict], bool]:
    used_fallback = False
    batch_size = 6
    total_batches = max(1, math.ceil(len(segments) / batch_size))

    for batch_index, batch in enumerate(_chunked(segments, batch_size), start=1):
        batch_payload = [
            {
                "id": segment["id"],
                "start": round(float(segment["start"]), 1),
                "end": round(float(segment["end"]), 1),
                "transcript": _compact_text(segment.get("transcript", ""), 220),
            }
            for segment in batch
        ]

        if log_cb:
            log_cb(f"Batch planner {batch_index}/{total_batches}: {len(batch_payload)} segmen")

        items = _request_batch_items(
            client=client,
            model_name=model_name,
            batch_payload=batch_payload,
            batch_index=batch_index,
            total_batches=total_batches,
            log_cb=log_cb,
        )
        if not items:
            used_fallback = True
        _apply_batch_items(batch, items)

    return segments, used_fallback


def _request_batch_items(client, model_name: str, batch_payload: list[dict], batch_index: int, total_batches: int, log_cb=None) -> list[dict]:
    prompt = _build_batch_prompt(batch_payload)
    last_error = None
    raw_text = ""
    models_to_try = [model_name] + [
        candidate for candidate in settings.get_recommended_json_models() if candidate != model_name
    ]

    for active_model in models_to_try:
        if log_cb and active_model != model_name:
            log_cb(
                f"Batch {batch_index}/{total_batches}: naik ke model fallback {active_model} "
                "agar JSON lebih stabil."
            )

        for attempt in range(1, 4):
            try:
                config = AIHandler.prepare_config(
                    temperature=0.15,
                    max_tokens=2200,
                    mime_type="application/json",
                    schema=PLANNER_BATCH_SCHEMA,
                )
                response = client.models.generate_content(
                    model=active_model,
                    contents=prompt,
                    config=config,
                )
                raw_text, parsed_payload = get_response_payload(response)
                data = _parse_plan_batch_json(raw_text, parsed_payload)
                items = data.get("items", [])
                if isinstance(items, list) and items:
                    return items
                raise ValueError("Respons planner tidak berisi items yang valid.")
            except Exception as e:
                last_error = e
                if log_cb:
                    log_cb(
                        f"Batch {batch_index}/{total_batches} model {active_model} "
                        f"attempt {attempt} gagal: {e}"
                    )
                prompt = _build_retry_batch_prompt(batch_payload, raw_text)

    if log_cb:
        snippet = raw_text[:400].replace("\n", "\\n") if raw_text else "-"
        log_cb(
            f"Batch {batch_index}/{total_batches} gagal total. "
            f"Pakai default lokal. Error terakhir: {last_error}. Snippet: {snippet}"
        )
    return []


def _build_batch_prompt(batch_payload: list[dict]) -> str:
    return (
        PLANNER_SYSTEM_PROMPT
        + "\n\nInput segmen:\n"
        + json.dumps(batch_payload, ensure_ascii=False, indent=2)
    )


def _build_retry_batch_prompt(batch_payload: list[dict], bad_json: str) -> str:
    retry_note = (
        "\n\nRespons sebelumnya tidak valid atau terpotong. "
        "Ulangi dari awal dan kembalikan JSON ringkas yang valid saja."
    )
    if bad_json:
        retry_note += "\nContoh respons rusak sebelumnya:\n" + bad_json[:1000]
    return _build_batch_prompt(batch_payload) + retry_note


def _parse_plan_batch_json(raw_text: str, parsed_payload=None) -> dict:
    if isinstance(parsed_payload, dict):
        return parsed_payload
    return parse_json_object(raw_text)


def _apply_batch_items(batch: list[dict], items: list[dict]):
    item_map = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except Exception:
            continue
        item_map[item_id] = item

    for segment in batch:
        item = item_map.get(segment["id"])
        if not item:
            continue
        segment["broll_keywords"] = _sanitize_keywords(item.get("k") or item.get("broll_keywords"))
        segment["transition_in"] = "cut"
        segment["transition_out"] = "cut"
        segment["effect"] = "static"
        segment["color_grade"] = "neutral"
        segment["emphasis_text"] = _sanitize_emphasis(item.get("emp", item.get("emphasis_text")))


def _chunked(items: list[dict], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _cap_emphasis_segments(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments

    max_allowed = max(1, int(len(segments) * 0.3))
    used = 0
    for segment in segments:
        if segment.get("emphasis_text"):
            used += 1
            if used > max_allowed:
                segment["emphasis_text"] = None
    return segments


def _sanitize_keywords(value) -> list[str]:
    if not isinstance(value, list):
        return ["nature"]
    keywords = [str(item).strip() for item in value if str(item).strip()]
    return keywords[:3] or ["nature"]


def _sanitize_transition(value, fallback: str) -> str:
    value = str(value or "").strip()
    return value if value in AVAILABLE_TRANSITIONS else fallback


def _sanitize_effect(value) -> str:
    value = str(value or "").strip()
    return value if value in AVAILABLE_EFFECTS else "static"


def _sanitize_grade(value) -> str:
    value = str(value or "").strip()
    return value if value in AVAILABLE_GRADES else "neutral"


def _sanitize_emphasis(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _looks_like_sentence_break(text: str) -> bool:
    stripped = str(text or "").strip()
    return stripped.endswith((".", "!", "?", "..."))


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(str(text or "").split()).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _fallback_segments_from_transcript(raw_segments: list[dict], total_duration: float) -> list[dict]:
    fallback = []
    for i, raw in enumerate(raw_segments):
        start = float(raw.get("start", 0))
        end = float(raw.get("end", start + 1))
        if end <= start:
            end = min(total_duration, start + 1.0)
        transcript = str(raw.get("text", "")).strip()
        fallback.append(
            {
                "id": i,
                "start": start,
                "end": end,
                "render_duration": max(1.0, end - start),
                "transcript": transcript,
                "subtitle_text": transcript,
                "broll_keywords": ["nature"],
                "broll_chosen": None,
                "broll_candidates": [],
                "transition_in": "cut",
                "transition_out": "cut",
                "effect": "static",
                "color_grade": "neutral",
                "emphasis_text": None,
                "floating_text_mode": "inherit",
                "confirmed": False,
            }
        )
    return fallback


def save_plan(plan: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[Planner] Plan disimpan ke {path}")


def load_plan(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
