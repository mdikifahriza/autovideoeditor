# ─────────────────────────────────────────────
#  core/broll_fetcher.py  —  B-roll Search & Download
# ─────────────────────────────────────────────
"""
Cari kandidat B-roll dari Pexels (utama) + Pixabay (fallback).
Download thumbnail dan video file ke cache.
"""

import os
import re
import time
import random
import requests

from core.project_manager import get_project_paths
from core.settings_manager import settings
from config import (
    BROLL_CANDIDATES, BROLL_CACHE_DIR,
    OUTPUT_WIDTH, OUTPUT_HEIGHT,
)

DOWNLOAD_RETRY_PER_CANDIDATE = 3
SEARCH_RETRY_ROUNDS = 4


def fetch_candidates_for_plan(plan: dict, project_dir: str = "", progress_cb=None, log_cb=None) -> dict:
    """
    Iterasi semua segmen dalam plan, cari kandidat B-roll tiap segmen.
    progress_cb(current, total, message) → optional callback untuk GUI.
    """
    segments = plan["segments"]
    total = len(segments)

    def _log(msg):
        print(f"[BrollFetcher] {msg}")
        if log_cb:
            log_cb(msg)

    for i, seg in enumerate(segments):
        keywords = seg["broll_keywords"]
        query = " ".join(keywords)
        duration_needed = seg["end"] - seg["start"]

        msg_prog = f"Mencari B-roll: '{query}'"
        if progress_cb:
            progress_cb(i, total, msg_prog)
        _log(f"Segmen {i+1}: mencari '{query}'")

        candidates = _search_candidates(query, duration_needed)

        if not candidates and len(keywords) > 1:
            _log(f"  Tidak ketemu '{query}', mencoba '{keywords[0]}'")
            candidates = _search_candidates(keywords[0], duration_needed)

        _log(f"  Dapat {len(candidates)} kandidat. Mendownload thumbnail...")
        for c in candidates:
            thumb_path, thumb_rel = _download_thumbnail(
                c["thumbnail_url"],
                c["id"],
                project_dir=project_dir,
            )
            c["thumbnail_path"] = thumb_path
            c["project_thumbnail_path"] = thumb_rel

        seg["broll_candidates"] = candidates
        seg["broll_chosen"] = candidates[0] if candidates else None

        time.sleep(0.3)

    if progress_cb:
        progress_cb(total, total, "B-roll selesai")

    return plan


# ── Search ────────────────────────────────────────────────────────────────────

def _search_candidates(query: str, min_duration: float) -> list[dict]:
    """Cari di Pexels dulu, kalau kurang fallback ke Pixabay."""
    results = _search_pexels(query, min_duration)
    if len(results) < 2:
        results += _search_pixabay(query, min_duration)
    deduped = []
    seen_ids = set()
    for candidate in results:
        candidate_id = str(candidate.get("id", "") or "").strip()
        if not candidate_id or candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        deduped.append(candidate)
        if len(deduped) >= BROLL_CANDIDATES:
            break
    return deduped


def _generate_veo(query: str, min_duration: float, project_dir: str = "") -> list[dict]:
    """Generate a video using Vertex AI Veo-2.0 via google-genai SDK."""
    from core.ai_handler import AIHandler, VideoGenerationError
    from core.settings_manager import settings
    from google import genai
    from google.genai import types
    import time
    
    try:
        client = AIHandler.get_client()
        
        operation = client.models.generate_videos(
            model='veo-2.0-generate-001',
            prompt=query,
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                aspect_ratio="16:9",
                person_generation="DONT_ALLOW"
            )
        )
        
        while not operation.done:
            time.sleep(5)
            operation = client.operations.get(name=operation.name)

        if not operation.response or not operation.response.generated_videos:
            return []

        generated_video = operation.response.generated_videos[0]
        
        video_id = f"veo_{int(time.time())}"
        
        videos_dir = os.path.join(project_dir, "exports") if project_dir else os.path.join(settings.get("projects_root", ""), "veo_videos")
        os.makedirs(videos_dir, exist_ok=True)
        local_path = os.path.join(videos_dir, f"{video_id}.mp4")
        
        with open(local_path, "wb") as f:
            f.write(generated_video.video.video_bytes)

        return [{
            "id": video_id,
            "url": "veo://generated",
            "source": "veo",
            "video_url": "veo://generated",
            "thumbnail_url": "", 
            "duration": 5.0, 
            "local_path": local_path,
            "project_local_path": os.path.relpath(local_path, project_dir).replace("\\", "/") if project_dir else ""
        }]
    except Exception as e:
        print(f"Veo error: {e}")
        return []

def _search_pexels(query: str, min_duration: float) -> list[dict]:
    api_key = settings.get("pexels_api_key", "")
    if not api_key or api_key.startswith("GANTI"):
        return []

    headers = {"Authorization": api_key}
    params  = {
        "query": query,
        "per_page": 15,
        "orientation": "landscape",
        "size": "large",
    }
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers, params=params, timeout=10
        )
        if r.status_code != 200:
            return []

        videos = r.json().get("videos", [])
        random.shuffle(videos)

        results = []
        for v in videos:
            if v.get("duration", 0) < min_duration:
                continue
            if int(v.get("width", 0) or 0) < int(v.get("height", 0) or 0):
                continue
            # Cari file HD (1280+)
            video_url = None
            for vf in sorted(v.get("video_files", []),
                             key=lambda x: x.get("width", 0), reverse=True):
                if vf.get("width", 0) >= 1280 and vf.get("width", 0) >= vf.get("height", 0):
                    video_url = vf["link"]
                    break
            if not video_url:
                continue

            thumbnail = v.get("image", "")
            results.append({
                "id":            f"pexels_{v['id']}",
                "source":        "pexels",
                "video_url":     video_url,
                "thumbnail_url": thumbnail,
                "thumbnail_path": None,
                "local_path":    None,
                "duration":      v.get("duration", 0),
                "width":         v.get("width", 1920),
                "height":        v.get("height", 1080),
            })
            if len(results) >= BROLL_CANDIDATES:
                break
        return results

    except Exception as e:
        print(f"[BrollFetcher] Pexels error '{query}': {e}")
        return []


def _search_pixabay(query: str, min_duration: float) -> list[dict]:
    api_key = settings.get("pixabay_api_key", "")
    if not api_key or api_key.startswith("GANTI"):
        return []

    params = {
        "key":        api_key,
        "q":          query,
        "video_type": "film",
        "per_page":   15,
        "min_width":  1280,
    }
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params=params, timeout=10
        )
        if r.status_code != 200:
            return []

        hits = r.json().get("hits", [])
        random.shuffle(hits)

        results = []
        for v in hits:
            if v.get("duration", 0) < min_duration:
                continue
            videos = v.get("videos", {})
            # Ambil large (1920) atau medium (1280)
            vf = videos.get("large") or videos.get("medium")
            if not vf:
                continue
            if int(vf.get("width", 0) or 0) < int(vf.get("height", 0) or 0):
                continue

            picture_id = v.get("picture_id", "")
            thumbnail_url = v.get("thumbnail_url", "") or v.get("picture_id", "")
            if thumbnail_url and not thumbnail_url.startswith("http") and picture_id:
                thumbnail_url = f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"

            results.append({
                "id":            f"pixabay_{v['id']}",
                "source":        "pixabay",
                "video_url":     vf["url"],
                "thumbnail_url": thumbnail_url,
                "thumbnail_path": None,
                "local_path":    None,
                "duration":      v.get("duration", 0),
                "width":         vf.get("width", 1280),
                "height":        vf.get("height", 720),
            })
            if len(results) >= BROLL_CANDIDATES:
                break
        return results

    except Exception as e:
        print(f"[BrollFetcher] Pixabay error '{query}': {e}")
        return []


# ── Download ──────────────────────────────────────────────────────────────────

def _download_thumbnail(url: str, video_id: str, project_dir: str = "") -> tuple[str | None, str | None]:
    """Download thumbnail ke cache, return local path."""
    if not url:
        return None, None

    safe_id = re.sub(r"[^a-z0-9_]", "_", video_id.lower())
    if project_dir:
        project_paths = get_project_paths(project_dir)
        base_dir = project_paths["generated_search"]
    else:
        base_dir = BROLL_CACHE_DIR
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"thumb_{safe_id}.jpg")
    rel_path = (
        os.path.relpath(path, project_dir).replace("\\", "/")
        if project_dir
        else None
    )

    if os.path.exists(path):
        return path, rel_path

    try:
        r = requests.get(url, timeout=10, stream=True)
        if r.status_code != 200:
            return None, None
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return path, rel_path
    except Exception:
        return None, None


def download_video(candidate: dict, project_dir: str = "", progress_cb=None) -> str | None:
    """
    Download video B-roll ke cache.
    Return local path, atau None jika gagal (akan di-track sebagai failed).
    """
    if candidate.get("local_path") and os.path.exists(candidate["local_path"]):
        candidate["download_status"] = "success"
        return candidate["local_path"]

    safe_id = re.sub(r"[^a-z0-9_]", "_", candidate["id"].lower())
    if project_dir:
        project_paths = get_project_paths(project_dir)
        base_dir = project_paths["generated_downloads"]
    else:
        base_dir = BROLL_CACHE_DIR
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"video_{safe_id}.mp4")

    if os.path.exists(path):
        candidate["local_path"] = path
        if project_dir:
            candidate["project_local_path"] = os.path.relpath(path, project_dir).replace("\\", "/")
        candidate["download_status"] = "success"
        return path

    url = candidate["video_url"]
    print(f"[BrollFetcher] Downloading {candidate['id']}...")

    last_error = ""
    for attempt in range(1, DOWNLOAD_RETRY_PER_CANDIDATE + 1):
        try:
            r = requests.get(url, stream=True, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            total_size = int(r.headers.get("content-length", 0) or 0)
            downloaded = 0
            start_ts = time.time()
            with open(path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        elapsed = max(0.001, time.time() - start_ts)
                        speed = downloaded / elapsed
                        total_mb = total_size / 1024.0 / 1024.0 if total_size else 0.0
                        done_mb = downloaded / 1024.0 / 1024.0
                        progress_cb(
                            downloaded,
                            total_size,
                            f"Downloading {candidate['id']} {done_mb:.1f}/{total_mb:.1f} MB @ {speed/1024/1024:.2f} MB/s",
                        )
            candidate["local_path"] = path
            if project_dir:
                candidate["project_local_path"] = os.path.relpath(path, project_dir).replace("\\", "/")
            candidate["download_status"] = "success"
            candidate.pop("download_error", None)
            return path
        except Exception as e:
            last_error = str(e)[:120]
            print(f"[BrollFetcher] Download attempt {attempt} failed for {candidate['id']}: {e}")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            time.sleep(0.8)

    candidate["download_status"] = "failed"
    candidate["download_error"] = last_error or "download failed"
    return None


def ensure_segment_video_available(
    segment: dict,
    project_dir: str = "",
    progress_cb=None,
    log_cb=None,
    max_search_rounds: int = SEARCH_RETRY_ROUNDS,
) -> str | None:
    if not isinstance(segment, dict):
        return None

    def _log(message: str):
        print(f"[BrollFetcher] {message}")
        if log_cb:
            log_cb(message)

    def _candidate_id(candidate: dict) -> str:
        return str(candidate.get("id", "") or "").strip().lower()

    def _ordered_candidates() -> list[dict]:
        chosen = segment.get("broll_chosen")
        ordered = []
        seen = set()
        for candidate in [chosen, *segment.get("broll_candidates", [])]:
            if not isinstance(candidate, dict):
                continue
            cid = _candidate_id(candidate)
            if not cid or cid in seen:
                continue
            seen.add(cid)
            ordered.append(candidate)
        return ordered

    def _try_candidates(candidates: list[dict]) -> str | None:
        for candidate in candidates:
            candidate_id = _candidate_id(candidate)
            if not candidate_id:
                continue
            local_path = candidate.get("local_path")
            if local_path and os.path.exists(local_path):
                segment["broll_chosen"] = candidate
                segment["broll_load_failed"] = False
                segment.pop("broll_load_error", None)
                return local_path
            _log(f"Mencoba download kandidat {candidate.get('id', '-')}.")
            local_path = download_video(candidate, project_dir=project_dir, progress_cb=progress_cb)
            if local_path and os.path.exists(local_path):
                segment["broll_chosen"] = candidate
                segment["broll_load_failed"] = False
                segment.pop("broll_load_error", None)
                return local_path
        return None

    existing = _try_candidates(_ordered_candidates())
    if existing:
        return existing

    keywords = [str(item).strip() for item in segment.get("broll_keywords", []) if str(item).strip()]
    queries = []
    if keywords:
        queries.append(" ".join(keywords))
        if len(keywords) > 1:
            queries.extend(keywords)
    transcript = " ".join(str(segment.get("transcript", "") or "").split())
    if transcript:
        queries.append(" ".join(transcript.split()[:6]))
    if not queries:
        queries.append("stock footage landscape")

    seen_queries = set()
    normalized_queries = []
    for query in queries:
        key = query.lower()
        if key and key not in seen_queries:
            seen_queries.add(key)
            normalized_queries.append(query)

    duration_needed = float(segment.get("render_duration") or 0) or max(
        1.0,
        float(segment.get("end", 0) or 0) - float(segment.get("start", 0) or 0),
    )

    exclude_ids = {
        _candidate_id(candidate)
        for candidate in segment.get("broll_candidates", [])
        if isinstance(candidate, dict)
    }

    for round_index in range(max(1, int(max_search_rounds or 1))):
        for query in normalized_queries:
            _log(f"Round {round_index + 1}: mencari fallback B-roll untuk '{query}'.")
            fresh_candidates = search_new_broll(
                query,
                duration_needed,
                exclude_ids=list(exclude_ids),
                project_dir=project_dir,
            )
            if not fresh_candidates:
                continue
            for candidate in fresh_candidates:
                cid = _candidate_id(candidate)
                if cid and cid not in exclude_ids:
                    segment.setdefault("broll_candidates", []).append(candidate)
                    exclude_ids.add(cid)
            local_path = _try_candidates(fresh_candidates)
            if local_path:
                return local_path
        time.sleep(0.6)

    segment["broll_load_failed"] = True
    segment["broll_load_error"] = "Semua kandidat B-roll dari provider yang tersedia gagal didownload."
    return None


def search_new_broll(query: str, min_duration: float,
                     exclude_ids: list[str] = None, project_dir: str = "") -> list[dict]:
    """
    Cari B-roll baru (untuk tombol Re-search di GUI).
    exclude_ids: list ID yang sudah pernah dipakai.
    """
    candidates = _search_candidates(query, min_duration)
    if exclude_ids:
        candidates = [c for c in candidates if c["id"] not in exclude_ids]

    for c in candidates:
        thumb_path, thumb_rel = _download_thumbnail(
            c["thumbnail_url"],
            c["id"],
            project_dir=project_dir,
        )
        c["thumbnail_path"] = thumb_path
        c["project_thumbnail_path"] = thumb_rel

    return candidates
