import os

from core.asset_manager import resolve_project_path
from core.cache_manager import get_output_cache_paths
from core.preview_cache_manager import clear_project_preview_cache
from core.project_manager import (
    attach_generated_voiceover,
    get_project_paths,
    read_project_metadata,
    save_tts_metadata,
    set_project_stage,
    update_project_metadata,
)
from core.tts_provider import GeminiTTSProvider


def _safe_remove(path: str):
    if not path or not os.path.exists(path):
        return
    try:
        os.remove(path)
    except Exception:
        pass


def invalidate_project_pipeline(project_dir: str):
    output_paths = get_output_cache_paths(project_dir)
    _safe_remove(output_paths["transcript"])
    _safe_remove(output_paths["plan"])
    _safe_remove(output_paths["search"])
    clear_project_preview_cache(project_dir)
    try:
        set_project_stage(project_dir, "transcription", "not_started")
        set_project_stage(project_dir, "planning", "not_started")
        set_project_stage(project_dir, "broll_search", "not_started")
        set_project_stage(project_dir, "validation", "not_started")
        set_project_stage(project_dir, "review", "not_started")
        set_project_stage(project_dir, "preview_render", "not_started")
    except Exception:
        pass


def get_active_voiceover_path(project_dir: str) -> str:
    metadata = read_project_metadata(project_dir)
    rel_path = metadata.get("inputs", {}).get("voiceover_file", "")
    return resolve_project_path(rel_path, project_dir, rel_path) or get_project_paths(project_dir)["audio"]


def synthesize_project_voiceover(
    project_dir: str,
    script_text: str,
    voice_name: str = "",
    model_name: str | None = None,
    log_cb=None,
) -> dict:
    project_paths = get_project_paths(project_dir)
    os.makedirs(os.path.dirname(project_paths["tts_audio"]), exist_ok=True)

    set_project_stage(project_dir, "tts_generation", "in_progress")
    provider = GeminiTTSProvider()
    result = provider.synthesize(
        text=script_text,
        output_path=project_paths["tts_audio"],
        voice_name=voice_name,
        model_name=model_name,
        log_cb=log_cb,
    )
    final_voiceover = attach_generated_voiceover(project_dir, result["audio_path"])
    save_tts_metadata(
        project_dir,
        provider=result.get("provider", "gemini"),
        voice_id=result.get("voice_id", voice_name),
        options={
            "model_name": result.get("model_name", ""),
            "chunks": int(result.get("chunks", 0) or 0),
            "sample_rate": int(result.get("sample_rate", 0) or 0),
        },
    )
    update_project_metadata(
        project_dir,
        content={
            "audio_origin": "tts",
        },
        artifacts={
            "tts_audio_file": os.path.relpath(project_paths["tts_audio"], project_dir).replace("\\", "/"),
        },
    )
    invalidate_project_pipeline(project_dir)
    set_project_stage(project_dir, "tts_generation", "done")
    return {
        **result,
        "project_audio_path": final_voiceover,
    }
