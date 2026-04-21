import glob
import json
import os

from config import BROLL_CACHE_DIR
from core.preview_cache_manager import clear_all_preview_cache, clear_project_preview_cache
from core.project_manager import get_project_paths

TRANSCRIPT_CACHE = "transcript_cache.json"
PIPELINE_STATE = "pipeline_state.json"


def _safe_load_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _safe_save_json(data: dict, path: str):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_output_cache_paths(output_dir: str) -> dict:
    project_paths = get_project_paths(output_dir)
    return {
        "transcript": project_paths["transcript"],
        "plan": project_paths["plan"],
        "draft": project_paths["draft"],
        "final": project_paths["final"],
        "project": project_paths["archive"],
        "state": project_paths["state"],
        "search": project_paths["search"],
        "log": project_paths["log"],
    }


def save_transcript_cache(output_dir: str, audio_path: str, segments: list[dict], total_duration: float):
    meta = {
        "audio_path": os.path.abspath(audio_path),
        "audio_size": os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
        "audio_mtime": os.path.getmtime(audio_path) if os.path.exists(audio_path) else 0,
        "segments": segments,
        "total_duration": total_duration,
    }
    _safe_save_json(meta, get_output_cache_paths(output_dir)["transcript"])


def load_transcript_cache(output_dir: str, audio_path: str):
    path = get_output_cache_paths(output_dir)["transcript"]
    data = _safe_load_json(path)
    if not isinstance(data, dict):
        return None
    if os.path.abspath(data.get("audio_path", "")) != os.path.abspath(audio_path):
        return None
    if not os.path.exists(audio_path):
        return None
    if int(data.get("audio_size", 0)) != os.path.getsize(audio_path):
        return None
    return data


def clear_cache(output_dir: str = None) -> tuple[int, int]:
    """Remove preview/final MP4 files in a project and flush global B-roll cache."""
    removed = 0
    freed = 0

    if output_dir:
        try:
            preview_root = get_preview_cache_paths(output_dir)
            freed += get_directory_size(preview_root["root"])
            clear_project_preview_cache(output_dir)
        except Exception:
            pass
        project_paths = get_project_paths(output_dir)
        patterns = [
            os.path.join(project_paths["preview"], "*.mp4"),
            os.path.join(project_paths["render"], "*.mp4"),
            os.path.join(project_paths["exports"], "*.mp4"),
        ]
        for pattern in patterns:
            for path in glob.glob(pattern):
                try:
                    freed += os.path.getsize(path)
                    os.remove(path)
                    removed += 1
                except Exception:
                    pass

    if os.path.exists(BROLL_CACHE_DIR):
        for root, _, files in os.walk(BROLL_CACHE_DIR, topdown=False):
            for name in files:
                if name.lower().endswith(".mp4") or name.lower().endswith(".jpg"):
                    path = os.path.join(root, name)
                    try:
                        freed += os.path.getsize(path)
                        os.remove(path)
                        removed += 1
                    except Exception:
                        pass
            if not os.listdir(root):
                try:
                    os.rmdir(root)
                except Exception:
                    pass
    else:
        try:
            freed += get_directory_size(get_preview_cache_root())
            clear_all_preview_cache()
        except Exception:
            pass
    return removed, freed


def get_preview_cache_paths(output_dir: str) -> dict:
    from core.preview_cache_manager import get_project_preview_paths

    return get_project_preview_paths(output_dir)


def get_preview_cache_root() -> str:
    from core.preview_cache_manager import get_preview_cache_root as _get_preview_cache_root

    return _get_preview_cache_root()


def get_directory_size(path: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    total = 0
    for root, _, files in os.walk(path):
        for file in files:
            try:
                total += os.path.getsize(os.path.join(root, file))
            except Exception:
                pass
    return total


def format_bytes(value: int) -> str:
    if value <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"
