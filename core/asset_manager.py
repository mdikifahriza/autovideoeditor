"""
Helpers for importing user-provided media into a project folder.
"""

import os
import shutil
from pathlib import Path

from core.project_manager import get_project_paths


def _sanitize_filename(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    return safe or "asset.bin"


def import_media_to_project(source_path: str, output_dir: str, category: str) -> dict:
    """
    Copy a local file into the project output directory and return both
    absolute and relative paths for persistence.
    """
    if not source_path or not os.path.exists(source_path):
        raise FileNotFoundError(source_path or "asset tidak ditemukan")

    source = Path(source_path)
    project_paths = get_project_paths(output_dir)
    target_dir = Path(project_paths["source_imports"]) / category
    target_dir.mkdir(parents=True, exist_ok=True)

    base_name = _sanitize_filename(source.name)
    target = target_dir / base_name
    counter = 1
    while target.exists() and source.resolve() != target.resolve():
        stem = _sanitize_filename(source.stem)
        suffix = source.suffix
        target = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    if source.resolve() != target.resolve():
        shutil.copy2(source, target)

    relative_path = os.path.relpath(target, output_dir)
    return {
        "absolute_path": str(target.resolve()),
        "relative_path": relative_path.replace("\\", "/"),
        "filename": target.name,
    }


def resolve_project_path(path: str, output_dir: str, relative_path: str = None) -> str | None:
    """Resolve a project asset path that may be absolute or stored relatively."""
    if path and os.path.exists(path):
        return path
    if relative_path:
        candidate = os.path.join(output_dir, relative_path)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    if path:
        candidate = os.path.join(output_dir, path)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def create_video_thumbnail(video_path: str, output_dir: str, category: str, stem: str) -> dict | None:
    """Capture a thumbnail from a local video into the project assets folder."""
    try:
        from moviepy import VideoFileClip
    except Exception:
        return None

    project_paths = get_project_paths(output_dir)
    target_dir = Path(project_paths["generated_search"]) / category
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(f"{stem}.jpg")
    target = target_dir / filename

    try:
        clip = VideoFileClip(video_path, audio=False)
        frame_time = min(0.1, max(0, clip.duration / 2 if clip.duration else 0))
        clip.save_frame(str(target), t=frame_time)
        clip.close()
        return {
            "absolute_path": str(target.resolve()),
            "relative_path": os.path.relpath(target, output_dir).replace("\\", "/"),
            "filename": target.name,
        }
    except Exception:
        return None
