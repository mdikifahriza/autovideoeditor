import json
import os
import re
import shutil
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from core.settings_manager import settings

PROJECT_FILENAME = "project.json"

_PROJECT_STRUCTURE = {
    "source": ("voiceover", "imports"),
    "generated": ("transcript", "plans", "subtitles", "search", "downloads", "research", "script", "tts"),
    "preview": (),
    "render": (),
    "exports": (),
    "logs": (),
    "cache": (),
}

_DEFAULT_STATUS = {
    "research": "not_started",
    "scripting": "not_started",
    "tts_generation": "not_started",
    "transcription": "not_started",
    "planning": "not_started",
    "broll_search": "not_started",
    "validation": "not_started",
    "review": "not_started",
    "preview_render": "not_started",
    "final_render": "not_started",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_slug(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", str(name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "New Project"


def get_default_projects_root() -> str:
    root = settings.get("projects_root", "").strip()
    if root:
        return root
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "AutoVideoEditor Projects")


def ensure_project_structure(project_dir: str) -> dict:
    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)

    paths = {"project_dir": str(project_path.resolve())}
    for root_name, children in _PROJECT_STRUCTURE.items():
        root_path = project_path / root_name
        root_path.mkdir(parents=True, exist_ok=True)
        paths[root_name] = str(root_path.resolve())
        for child in children:
            child_path = root_path / child
            child_path.mkdir(parents=True, exist_ok=True)
            paths[f"{root_name}_{child}"] = str(child_path.resolve())
    return paths


def get_project_paths(project_dir: str) -> dict:
    paths = ensure_project_structure(project_dir)
    project_dir = paths["project_dir"]
    return {
        **paths,
        "metadata": os.path.join(project_dir, PROJECT_FILENAME),
        "audio": _find_voiceover_file(project_dir),
        "transcript": os.path.join(paths["generated_transcript"], "transcript.json"),
        "plan": os.path.join(paths["generated_plans"], "edit_plan.json"),
        "search": os.path.join(paths["generated_search"], "broll_search.json"),
        "research": os.path.join(paths["generated_research"], "research.json"),
        "script_draft": os.path.join(paths["generated_script"], "draft_script.txt"),
        "script_final": os.path.join(paths["generated_script"], "final_script.txt"),
        "tts_audio": os.path.join(paths["generated_tts"], "narration.wav"),
        "tts_manifest": os.path.join(paths["generated_tts"], "tts.json"),
        "subtitles": os.path.join(paths["generated_subtitles"], "subtitles.srt"),
        "draft": os.path.join(paths["preview"], "draft_video.mp4"),
        "final": os.path.join(paths["exports"], "final_video.mp4"),
        "archive": os.path.join(project_dir, "project.avep"),
        "state": os.path.join(project_dir, "pipeline_state.json"),
        "log": os.path.join(paths["logs"], "project.log"),
    }


def _find_voiceover_file(project_dir: str) -> str:
    voice_dir = Path(project_dir) / "source" / "voiceover"
    if not voice_dir.exists():
        return ""
    files = sorted(p for p in voice_dir.iterdir() if p.is_file())
    return str(files[0].resolve()) if files else ""


def _default_metadata(project_dir: str, name: str) -> dict:
    project_paths = get_project_paths(project_dir)
    now = _utc_now()
    return {
        "project_id": str(uuid.uuid4()),
        "name": name,
        "project_mode": "voiceover",
        "review_profile": "standard",
        "created_at": now,
        "updated_at": now,
        "project_dir": project_paths["project_dir"],
        "status": deepcopy(_DEFAULT_STATUS),
        "inputs": {
            "title": name,
            "voiceover_file": "",
            "manual_script_file": "",
            "research_query": "",
            "research_file": "",
            "tts_voice": settings.get("tts_voice_name", "Kore"),
            "tts_provider": settings.get("tts_provider", "gemini"),
            "intro_file": "",
            "outro_file": "",
        },
        "artifacts": {
            "script_file": "",
            "tts_audio_file": "",
            "transcript_file": "",
            "plan_file": "",
            "search_file": "",
            "subtitle_file": "",
            "preview_file": "",
            "final_file": "",
        },
        "content": {
            "script_file": "",
            "script_source": "",
            "audio_origin": "uploaded",
        },
        "settings_snapshot": {
            "model_profile": settings.get("model_profile", "balanced"),
            "video_encoder_mode": settings.get_video_encoder_mode(),
            "video_encoder_effective": settings.get_video_encoder_detection().get("detected", ""),
            "subtitle_enabled": False,
            "subtitle_style": "clean",
            "floating_text_enabled": False,
            "floating_text_font": "Segoe UI",
            "floating_text_size": 58,
            "floating_text_animation": "slide_up",
            "floating_text_position": "upper_third",
        },
        "last_error": "",
    }


def _relative_to_project(project_dir: str, target_path: str) -> str:
    if not target_path:
        return ""
    try:
        return os.path.relpath(target_path, project_dir).replace("\\", "/")
    except Exception:
        return str(target_path).replace("\\", "/")


def read_project_metadata(project_dir: str) -> dict:
    project_paths = get_project_paths(project_dir)
    metadata_path = project_paths["metadata"]
    if not os.path.exists(metadata_path):
        return _default_metadata(project_dir, os.path.basename(project_dir))

    with open(metadata_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    data.setdefault("status", deepcopy(_DEFAULT_STATUS))
    for key, value in _DEFAULT_STATUS.items():
        data["status"].setdefault(key, value)
    data.setdefault("inputs", {})
    data.setdefault("artifacts", {})
    data.setdefault("content", {})
    data.setdefault("settings_snapshot", {})
    data.setdefault("last_error", "")
    data.setdefault("project_mode", "voiceover")
    data.setdefault("review_profile", "standard")
    data["inputs"].setdefault("title", data.get("name", os.path.basename(project_dir)))
    data["inputs"].setdefault("voiceover_file", "")
    data["inputs"].setdefault("manual_script_file", "")
    data["inputs"].setdefault("research_query", "")
    data["inputs"].setdefault("research_file", "")
    data["inputs"].setdefault("tts_voice", settings.get("tts_voice_name", "Kore"))
    data["inputs"].setdefault("tts_provider", settings.get("tts_provider", "gemini"))
    data["inputs"].setdefault("intro_file", "")
    data["inputs"].setdefault("outro_file", "")
    data["artifacts"].setdefault("script_file", "")
    data["artifacts"].setdefault("tts_audio_file", "")
    data["content"].setdefault("script_file", "")
    data["content"].setdefault("script_source", "")
    data["content"].setdefault("audio_origin", "uploaded")
    data["project_dir"] = project_paths["project_dir"]
    return data


def write_project_metadata(project_dir: str, metadata: dict) -> dict:
    project_paths = get_project_paths(project_dir)
    metadata = deepcopy(metadata)
    metadata["project_dir"] = project_paths["project_dir"]
    metadata["updated_at"] = _utc_now()
    with open(project_paths["metadata"], "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    return metadata


def update_project_metadata(project_dir: str, **updates) -> dict:
    metadata = read_project_metadata(project_dir)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(metadata.get(key), dict):
            metadata[key].update(value)
        else:
            metadata[key] = value
    return write_project_metadata(project_dir, metadata)


def set_project_stage(project_dir: str, stage: str, status: str, error: str = "") -> dict:
    metadata = read_project_metadata(project_dir)
    metadata.setdefault("status", deepcopy(_DEFAULT_STATUS))
    metadata["status"][stage] = status
    if error:
        metadata["last_error"] = error
    elif metadata.get("last_error") and status in {"done", "in_progress"}:
        metadata["last_error"] = ""
    return write_project_metadata(project_dir, metadata)


def create_project(
    name: str,
    projects_root: str = "",
    voiceover_path: str = "",
    project_mode: str = "voiceover",
    review_profile: str = "standard",
    title: str = "",
) -> tuple[str, dict]:
    safe_name = _sanitize_slug(name)
    root = projects_root.strip() or get_default_projects_root()
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)

    project_dir = root_path / safe_name
    counter = 2
    while project_dir.exists():
        project_dir = root_path / f"{safe_name} {counter}"
        counter += 1

    ensure_project_structure(str(project_dir))
    metadata = _default_metadata(str(project_dir), project_dir.name)
    metadata["project_mode"] = str(project_mode or "voiceover").strip() or "voiceover"
    metadata["review_profile"] = str(review_profile or "standard").strip() or "standard"
    metadata["inputs"]["title"] = str(title or project_dir.name).strip() or project_dir.name
    metadata["content"]["audio_origin"] = "uploaded" if voiceover_path else ""
    metadata = write_project_metadata(str(project_dir), metadata)

    if voiceover_path:
        attach_voiceover(str(project_dir), voiceover_path)
        metadata = read_project_metadata(str(project_dir))

    return str(project_dir.resolve()), metadata


def attach_voiceover(project_dir: str, source_audio: str) -> str:
    if not source_audio or not os.path.exists(source_audio):
        raise FileNotFoundError(source_audio or "Voice over tidak ditemukan")

    project_paths = get_project_paths(project_dir)
    target_dir = Path(project_paths["source_voiceover"])
    source_path = Path(source_audio)
    target_path = target_dir / f"voiceover{source_path.suffix.lower()}"

    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)

    metadata = read_project_metadata(project_dir)
    metadata["inputs"]["voiceover_file"] = _relative_to_project(project_dir, str(target_path))
    metadata.setdefault("content", {})
    metadata["content"]["audio_origin"] = "uploaded"
    write_project_metadata(project_dir, metadata)
    return str(target_path.resolve())


def attach_generated_voiceover(project_dir: str, source_audio: str) -> str:
    target = attach_voiceover(project_dir, source_audio)
    metadata = read_project_metadata(project_dir)
    metadata.setdefault("content", {})
    metadata["content"]["audio_origin"] = "tts"
    write_project_metadata(project_dir, metadata)
    return target


def _write_text_file(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text or "")


def save_script_text(project_dir: str, text: str, kind: str = "final") -> str:
    project_paths = get_project_paths(project_dir)
    target_path = project_paths["script_draft"] if kind == "draft" else project_paths["script_final"]
    _write_text_file(target_path, text)

    metadata = read_project_metadata(project_dir)
    metadata.setdefault("artifacts", {})
    metadata.setdefault("content", {})
    rel_path = _relative_to_project(project_dir, target_path)
    metadata["artifacts"]["script_file"] = rel_path
    metadata["content"]["script_file"] = rel_path
    if kind == "draft" and not metadata["inputs"].get("manual_script_file"):
        metadata["inputs"]["manual_script_file"] = rel_path
    write_project_metadata(project_dir, metadata)
    return str(Path(target_path).resolve())


def attach_manual_script(project_dir: str, text: str, kind: str = "draft") -> str:
    path = save_script_text(project_dir, text, kind=kind)
    metadata = read_project_metadata(project_dir)
    metadata["inputs"]["manual_script_file"] = _relative_to_project(project_dir, path)
    metadata["content"]["script_source"] = "manual"
    write_project_metadata(project_dir, metadata)
    return path


def save_research_pack(project_dir: str, payload: dict, query: str = "") -> str:
    project_paths = get_project_paths(project_dir)
    os.makedirs(os.path.dirname(project_paths["research"]), exist_ok=True)
    with open(project_paths["research"], "w", encoding="utf-8") as fh:
        json.dump(payload or {}, fh, ensure_ascii=False, indent=2)

    metadata = read_project_metadata(project_dir)
    rel_path = _relative_to_project(project_dir, project_paths["research"])
    metadata["inputs"]["research_query"] = str(query or "").strip()
    metadata["inputs"]["research_file"] = rel_path
    write_project_metadata(project_dir, metadata)
    return str(Path(project_paths["research"]).resolve())


def save_tts_metadata(project_dir: str, provider: str, voice_id: str, options: dict | None = None) -> str:
    project_paths = get_project_paths(project_dir)
    payload = {
        "provider": str(provider or "").strip(),
        "voice_id": str(voice_id or "").strip(),
        "options": options or {},
        "updated_at": _utc_now(),
    }
    with open(project_paths["tts_manifest"], "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    metadata = read_project_metadata(project_dir)
    metadata["inputs"]["tts_provider"] = payload["provider"]
    metadata["inputs"]["tts_voice"] = payload["voice_id"]
    metadata["artifacts"]["tts_audio_file"] = _relative_to_project(project_dir, project_paths["tts_audio"])
    write_project_metadata(project_dir, metadata)
    return str(Path(project_paths["tts_manifest"]).resolve())


def load_script_text(project_dir: str) -> str:
    metadata = read_project_metadata(project_dir)
    project_paths = get_project_paths(project_dir)
    candidates = [
        metadata.get("content", {}).get("script_file", ""),
        metadata.get("artifacts", {}).get("script_file", ""),
        metadata.get("inputs", {}).get("manual_script_file", ""),
        _relative_to_project(project_dir, project_paths["script_final"]),
        _relative_to_project(project_dir, project_paths["script_draft"]),
    ]
    seen = set()
    for candidate in candidates:
        key = str(candidate or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        path = os.path.join(project_dir, key) if not os.path.isabs(key) else key
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    return ""


def register_artifact(project_dir: str, artifact_key: str, file_path: str, stage: str = "") -> dict:
    metadata = read_project_metadata(project_dir)
    metadata.setdefault("artifacts", {})
    metadata["artifacts"][artifact_key] = _relative_to_project(project_dir, file_path)
    if stage:
        metadata.setdefault("status", deepcopy(_DEFAULT_STATUS))
        metadata["status"][stage] = "done"
    return write_project_metadata(project_dir, metadata)


def append_project_log(project_dir: str, message: str):
    if not message:
        return
    project_paths = get_project_paths(project_dir)
    line = f"[{_utc_now()}] {message}\n"
    with open(project_paths["log"], "a", encoding="utf-8") as fh:
        fh.write(line)


def save_project(output_dir: str, avep_path: str):
    with zipfile.ZipFile(avep_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file_name in files:
                abs_path = os.path.join(root, file_name)
                if abs_path == avep_path:
                    continue
                rel_path = os.path.relpath(abs_path, output_dir)
                zipf.write(abs_path, rel_path)


def load_project(project_path: str, extract_to: str | None = None) -> dict:
    if os.path.isdir(project_path):
        project_paths = get_project_paths(project_path)
        metadata = read_project_metadata(project_path)
        plan = None
        if os.path.exists(project_paths["plan"]):
            with open(project_paths["plan"], "r", encoding="utf-8") as fh:
                plan = json.load(fh)
            plan = _rehydrate_project_paths(plan, project_path)
        return {
            "project_dir": project_paths["project_dir"],
            "metadata": metadata,
            "plan": plan,
            "audio_path": project_paths["audio"],
            "draft_path": project_paths["draft"],
            "final_path": project_paths["final"],
        }

    if not extract_to:
        raise ValueError("extract_to wajib diisi untuk membuka file .avep")

    try:
        if os.path.exists(extract_to):
            shutil.rmtree(extract_to, ignore_errors=True)
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(project_path, "r") as zipf:
            zipf.extractall(extract_to)
        return load_project(extract_to)
    except Exception as exc:
        print(f"[ProjectManager] Gagal membuka proyek: {exc}")
        return {}


def _rehydrate_project_paths(plan: dict, output_dir: str) -> dict:
    from core.asset_manager import resolve_project_path

    project_settings = plan.get("project_settings", {})
    for key in ("intro_video", "outro_video"):
        asset = project_settings.get(key)
        if isinstance(asset, dict):
            asset["absolute_path"] = resolve_project_path(
                asset.get("absolute_path"),
                output_dir,
                asset.get("relative_path"),
            )

    for segment in plan.get("segments", []):
        chosen = segment.get("broll_chosen")
        if isinstance(chosen, dict):
            chosen["local_path"] = resolve_project_path(
                chosen.get("local_path"),
                output_dir,
                chosen.get("project_local_path"),
            )
            chosen["thumbnail_path"] = resolve_project_path(
                chosen.get("thumbnail_path"),
                output_dir,
                chosen.get("project_thumbnail_path"),
            )

        candidates = []
        for candidate in segment.get("broll_candidates", []):
            if isinstance(candidate, dict):
                candidate["local_path"] = resolve_project_path(
                    candidate.get("local_path"),
                    output_dir,
                    candidate.get("project_local_path"),
                )
                candidate["thumbnail_path"] = resolve_project_path(
                    candidate.get("thumbnail_path"),
                    output_dir,
                    candidate.get("project_thumbnail_path"),
                )
            candidates.append(candidate)
        segment["broll_candidates"] = candidates

    return plan
