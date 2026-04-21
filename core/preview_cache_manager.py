import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def _candidate_roots() -> list[str]:
    roots = [r"C:\Temp\ProgramBRoll"]
    for env_key in ("TEMP", "TMP"):
        env_value = os.environ.get(env_key, "").strip()
        if env_value:
            roots.append(os.path.join(env_value, "ProgramBRoll"))
    roots.append(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "ProgramBRoll"))
    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for root in roots:
        normalized = os.path.abspath(root).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(root)
    return unique


def get_preview_cache_root() -> str:
    for root in _candidate_roots():
        try:
            Path(root).mkdir(parents=True, exist_ok=True)
            return str(Path(root).resolve())
        except Exception:
            continue
    fallback = os.path.join(os.getcwd(), ".preview_cache")
    Path(fallback).mkdir(parents=True, exist_ok=True)
    return str(Path(fallback).resolve())


def _project_key(project_dir: str) -> str:
    normalized = os.path.abspath(project_dir or "").replace("\\", "/").lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def get_project_preview_paths(project_dir: str) -> dict:
    root = Path(get_preview_cache_root()) / _project_key(project_dir)
    chunks = root / "chunks"
    drafts = root / "drafts"
    for folder in (root, chunks, drafts):
        folder.mkdir(parents=True, exist_ok=True)
    return {
        "root": str(root.resolve()),
        "chunks": str(chunks.resolve()),
        "drafts": str(drafts.resolve()),
        "manifest": str((root / "manifest.json").resolve()),
    }


def get_preview_chunk_path(project_dir: str, index: int) -> str:
    return os.path.join(get_project_preview_paths(project_dir)["chunks"], f"seg_{index:03d}.mp4")


def create_preview_draft_path(project_dir: str, ready_count: int) -> str:
    timestamp = int(time.time() * 1000)
    return os.path.join(
        get_project_preview_paths(project_dir)["drafts"],
        f"draft_ready_{ready_count:03d}_{timestamp}.mp4",
    )


def load_preview_manifest(project_dir: str) -> dict | None:
    manifest_path = get_project_preview_paths(project_dir)["manifest"]
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_preview_manifest(project_dir: str, manifest: dict) -> dict:
    manifest = dict(manifest or {})
    manifest["project_dir"] = os.path.abspath(project_dir)
    with open(get_project_preview_paths(project_dir)["manifest"], "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest


def build_preview_signature(plan: dict, audio_path: str) -> str:
    project_settings = dict((plan or {}).get("project_settings", {}))
    settings_payload = {
        "subtitle_enabled": bool(project_settings.get("subtitle_enabled", False)),
        "subtitle_style": project_settings.get("subtitle_style", "clean"),
        "intro_video": _asset_signature(project_settings.get("intro_video")),
        "outro_video": _asset_signature(project_settings.get("outro_video")),
        "floating_text_enabled": bool(project_settings.get("floating_text_enabled", False)),
        "floating_text_font": project_settings.get("floating_text_font", "Segoe UI"),
        "floating_text_size": int(project_settings.get("floating_text_size", 58) or 58),
        "floating_text_animation": project_settings.get("floating_text_animation", "slide_up"),
        "floating_text_position": project_settings.get("floating_text_position", "upper_third"),
    }
    audio_abspath = os.path.abspath(audio_path or "")
    audio_payload = {
        "path": audio_abspath,
        "exists": os.path.exists(audio_abspath),
        "size": os.path.getsize(audio_abspath) if os.path.exists(audio_abspath) else 0,
        "mtime": int(os.path.getmtime(audio_abspath)) if os.path.exists(audio_abspath) else 0,
    }
    segments_payload = []
    for segment in (plan or {}).get("segments", []):
        chosen = segment.get("broll_chosen") if isinstance(segment, dict) else {}
        segments_payload.append(
            {
                "id": segment.get("id"),
                "start": round(float(segment.get("start", 0) or 0), 3),
                "end": round(float(segment.get("end", 0) or 0), 3),
                "render_duration": round(
                    float(
                        segment.get("render_duration")
                        or max(1.0, float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0))
                    ),
                    3,
                ),
                "effect": segment.get("effect", "static"),
                "transition_in": segment.get("transition_in", "cut"),
                "transition_out": segment.get("transition_out", "cut"),
                "color_grade": segment.get("color_grade", "neutral"),
                "emphasis_text": segment.get("emphasis_text") or "",
                "floating_text_mode": segment.get("floating_text_mode", "inherit") or "inherit",
                "subtitle_text": segment.get("subtitle_text") or segment.get("transcript") or "",
                "broll": _asset_signature(chosen),
            }
        )
    payload = {
        "audio": audio_payload,
        "project_settings": settings_payload,
        "segments": segments_payload,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def prepare_preview_manifest(project_dir: str, plan: dict, audio_path: str, start_index: int = 0) -> dict:
    segment_total = len((plan or {}).get("segments", []))
    signature = build_preview_signature(plan, audio_path)
    manifest = load_preview_manifest(project_dir) or {}
    is_compatible = (
        manifest.get("plan_signature") == signature
        and int(manifest.get("segment_total", 0) or 0) == segment_total
    )
    if not is_compatible:
        clear_project_preview_cache(project_dir)
        manifest = {}

    chunks = []
    existing_chunks = manifest.get("chunks", []) if is_compatible else []
    for index in range(segment_total):
        entry = existing_chunks[index] if index < len(existing_chunks) else {}
        path = entry.get("path") or get_preview_chunk_path(project_dir, index)
        if index < start_index and entry.get("status") == "ready" and os.path.exists(path):
            chunks.append(
                {
                    "index": index,
                    "status": "ready",
                    "path": path,
                    "duration": float(entry.get("duration", 0) or 0),
                }
            )
            continue

        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        chunks.append(
            {
                "index": index,
                "status": "pending",
                "path": get_preview_chunk_path(project_dir, index),
                "duration": 0.0,
            }
        )

    draft_path = manifest.get("draft_path", "") if is_compatible else ""
    if draft_path and not os.path.exists(draft_path):
        draft_path = ""

    refreshed = {
        "project_dir": os.path.abspath(project_dir),
        "plan_signature": signature,
        "audio_path": os.path.abspath(audio_path or ""),
        "segment_total": segment_total,
        "chunks": chunks,
        "draft_path": draft_path,
        "ready_count": count_ready_prefix({"chunks": chunks}),
        "available_duration": float(manifest.get("available_duration", 0) or 0) if draft_path else 0.0,
        "updated_at": int(time.time()),
    }
    return save_preview_manifest(project_dir, refreshed)


def count_ready_prefix(manifest: dict) -> int:
    ready = 0
    for chunk in manifest.get("chunks", []):
        if chunk.get("status") == "ready" and os.path.exists(chunk.get("path", "")):
            ready += 1
            continue
        break
    return ready


def get_ready_chunk_paths(manifest: dict) -> list[str]:
    ready_paths = []
    for chunk in manifest.get("chunks", []):
        path = chunk.get("path", "")
        if chunk.get("status") == "ready" and path and os.path.exists(path):
            ready_paths.append(path)
            continue
        break
    return ready_paths


def update_chunk_ready(project_dir: str, manifest: dict, index: int, path: str, duration: float) -> dict:
    chunks = manifest.setdefault("chunks", [])
    while len(chunks) <= index:
        chunks.append(
            {
                "index": len(chunks),
                "status": "pending",
                "path": get_preview_chunk_path(project_dir, len(chunks)),
                "duration": 0.0,
            }
        )
    chunks[index] = {
        "index": index,
        "status": "ready",
        "path": path,
        "duration": float(duration or 0),
    }
    manifest["ready_count"] = count_ready_prefix(manifest)
    manifest["updated_at"] = int(time.time())
    return save_preview_manifest(project_dir, manifest)


def update_draft_state(project_dir: str, manifest: dict, draft_path: str, available_duration: float) -> dict:
    manifest["draft_path"] = draft_path
    manifest["available_duration"] = float(available_duration or 0)
    manifest["ready_count"] = count_ready_prefix(manifest)
    manifest["updated_at"] = int(time.time())
    cleanup_old_drafts(project_dir, keep=draft_path)
    return save_preview_manifest(project_dir, manifest)


def cleanup_old_drafts(project_dir: str, keep: str = ""):
    drafts_dir = get_project_preview_paths(project_dir)["drafts"]
    if not os.path.exists(drafts_dir):
        return
    keep_norm = os.path.abspath(keep).lower() if keep else ""
    drafts = sorted(
        (os.path.join(drafts_dir, name) for name in os.listdir(drafts_dir) if name.lower().endswith(".mp4")),
        key=lambda item: os.path.getmtime(item),
        reverse=True,
    )
    protected = set()
    if keep_norm:
        protected.add(keep_norm)
    for draft in drafts[:2]:
        protected.add(os.path.abspath(draft).lower())
    for draft in drafts:
        if os.path.abspath(draft).lower() in protected:
            continue
        try:
            os.remove(draft)
        except Exception:
            pass


def get_latest_preview_draft_path(project_dir: str, plan: dict | None = None, audio_path: str = "") -> str:
    manifest = load_preview_manifest(project_dir)
    if not manifest:
        return ""
    if plan is not None and manifest.get("plan_signature") != build_preview_signature(plan, audio_path):
        return ""
    draft_path = manifest.get("draft_path", "")
    return draft_path if draft_path and os.path.exists(draft_path) else ""


def clear_project_preview_cache(project_dir: str):
    preview_root = get_project_preview_paths(project_dir)["root"]
    shutil.rmtree(preview_root, ignore_errors=True)


def clear_all_preview_cache():
    shutil.rmtree(get_preview_cache_root(), ignore_errors=True)


def _asset_signature(asset) -> str:
    if not isinstance(asset, dict):
        return ""
    return (
        str(asset.get("relative_path") or "").strip()
        or str(asset.get("project_local_path") or "").strip()
        or str(asset.get("local_path") or "").strip()
        or str(asset.get("absolute_path") or "").strip()
        or str(asset.get("video_url") or "").strip()
        or str(asset.get("id") or "").strip()
    )
