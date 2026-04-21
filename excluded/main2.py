import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from config import OUTPUT_BITRATE, OUTPUT_FPS, OUTPUT_HEIGHT, OUTPUT_WIDTH
from core.cache_manager import save_transcript_cache
from core.asset_manager import resolve_project_path
from core.broll_fetcher import fetch_candidates_for_plan, search_new_broll
from core.planner import generate_edit_plan, save_plan
from core.project_manager import attach_voiceover, create_project, get_project_paths, load_project
from core.resource_guard import wait_until_memory_below
from core.transcriber import transcribe
from core.video_encoder_manager import find_ffmpeg_executable, get_effective_video_encoder

FALLBACK_ALT_LIMIT = 3
DOWNLOAD2_DIRNAME = "download 2"
MAIN2_TRANSCRIBE_MODEL = "gemini-2.5-flash"
MEDIA_SEARCH_ROUNDS = 3


def _log(msg: str):
    print(f"[main2] {msg}")


def _run_ffmpeg(cmd: list[str], label: str):
    _log(f"Jalankan {label}...")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-1800:]
        raise RuntimeError(f"FFmpeg [{label}] gagal (code {proc.returncode}):\n{tail}")


def _encoder_args(encoder: str, bitrate: str) -> list[str]:
    if encoder == "h264_qsv":
        return [
            "-c:v",
            "h264_qsv",
            "-b:v",
            bitrate,
            "-look_ahead",
            "0",
            "-async_depth",
            "1",
        ]
    return [
        "-c:v",
        "libx264",
        "-b:v",
        bitrate,
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
    ]


def _run_encode_with_fallback(
    base_cmd: list[str],
    output_path: str,
    encoder: str,
    bitrate: str,
    label: str,
):
    cmd = [*base_cmd, *_encoder_args(encoder, bitrate), "-movflags", "+faststart", output_path]
    try:
        _run_ffmpeg(cmd, label=label)
        return
    except Exception as exc:
        if encoder != "h264_qsv":
            raise
        _log(f"{label}: h264_qsv gagal, fallback ke libx264. Detail: {exc}")

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    fallback_cmd = [*base_cmd, *_encoder_args("libx264", bitrate), "-movflags", "+faststart", output_path]
    _run_ffmpeg(fallback_cmd, label=f"{label} fallback_libx264")


def _safe_duration(segment: dict) -> float:
    try:
        render_duration = float(segment.get("render_duration") or 0.0)
    except Exception:
        render_duration = 0.0
    if render_duration > 0:
        return max(0.5, render_duration)
    try:
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start + 1.0) or (start + 1.0))
    except Exception:
        return 1.0
    if end <= start:
        return 1.0
    return max(0.5, end - start)


def _candidate_id(candidate: dict) -> str:
    return str(candidate.get("id", "") or "").strip().lower()


def _project_download2_dir(project_dir: str) -> str:
    target = os.path.join(project_dir, DOWNLOAD2_DIRNAME)
    os.makedirs(target, exist_ok=True)
    return target


def _safe_candidate_filename(candidate: dict) -> str:
    cid = _candidate_id(candidate) or "unknown"
    cid = re.sub(r"[^a-z0-9_]+", "_", cid)
    return f"video_{cid}.mp4"


def _adopt_to_download2(existing_path: str, candidate: dict, project_dir: str) -> str | None:
    if not existing_path or not os.path.exists(existing_path):
        return None
    download2_dir = _project_download2_dir(project_dir)
    out_path = os.path.join(download2_dir, _safe_candidate_filename(candidate))
    if os.path.abspath(existing_path) != os.path.abspath(out_path):
        try:
            shutil.copy2(existing_path, out_path)
        except Exception as exc:
            _log(f"Gagal salin aset ke '{DOWNLOAD2_DIRNAME}': {exc}")
            return os.path.abspath(existing_path)
    candidate["local_path"] = os.path.abspath(out_path)
    candidate["project_local_path"] = os.path.relpath(out_path, project_dir).replace("\\", "/")
    return os.path.abspath(out_path)


def _download_candidate_to_download2(candidate: dict, project_dir: str) -> str | None:
    url = str(candidate.get("video_url", "") or "").strip()
    if not url:
        return None

    download2_dir = _project_download2_dir(project_dir)
    out_path = os.path.join(download2_dir, _safe_candidate_filename(candidate))
    if os.path.exists(out_path):
        candidate["local_path"] = os.path.abspath(out_path)
        candidate["project_local_path"] = os.path.relpath(out_path, project_dir).replace("\\", "/")
        candidate["download_status"] = "success"
        return os.path.abspath(out_path)

    try:
        _log(f"Download ke {DOWNLOAD2_DIRNAME}: {candidate.get('id', '-')}")
        resp = requests.get(url, stream=True, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        with open(out_path, "wb") as fh:
            for chunk in resp.iter_content(65536):
                if chunk:
                    fh.write(chunk)
        candidate["local_path"] = os.path.abspath(out_path)
        candidate["project_local_path"] = os.path.relpath(out_path, project_dir).replace("\\", "/")
        candidate["download_status"] = "success"
        candidate.pop("download_error", None)
        return os.path.abspath(out_path)
    except Exception as exc:
        candidate["download_status"] = "failed"
        candidate["download_error"] = str(exc)[:180]
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        return None


def _resolve_candidate_existing_path(candidate: dict, project_dir: str) -> str | None:
    direct = candidate.get("local_path")
    if direct and os.path.exists(direct):
        return _adopt_to_download2(direct, candidate, project_dir)
    resolved = resolve_project_path(
        candidate.get("local_path"),
        project_dir,
        candidate.get("project_local_path"),
    )
    if resolved and os.path.exists(resolved):
        return _adopt_to_download2(resolved, candidate, project_dir)
    return None


def _dedupe_candidates(candidates: list[dict], limit: int | None = None) -> list[dict]:
    dedup = []
    seen = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        cid = _candidate_id(item)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        dedup.append(item)
        if limit and len(dedup) >= limit:
            break
    return dedup


def _segment_fallback_queries(segment: dict) -> list[str]:
    queries = []
    keywords = [str(item).strip() for item in segment.get("broll_keywords", []) if str(item).strip()]
    if keywords:
        queries.append(" ".join(keywords))
        queries.extend(keywords)
    transcript = " ".join(str(segment.get("transcript", "") or "").split())
    if transcript:
        queries.append(" ".join(transcript.split()[:6]))
    if not queries:
        queries.append("stock footage landscape")
    normalized = []
    seen = set()
    for query in queries:
        key = query.lower().strip()
        if key and key not in seen:
            seen.add(key)
            normalized.append(query)
    return normalized


def _enrich_segment_media_fallbacks(segment: dict, project_dir: str, target_count: int = FALLBACK_ALT_LIMIT):
    existing = _dedupe_candidates(segment.get("broll_candidates", []), limit=target_count)
    if len(existing) >= target_count:
        segment["main2_media_fallbacks"] = existing
        segment["broll_candidates"] = existing
        segment["broll_chosen"] = None
        return

    result = list(existing)
    exclude_ids = {_candidate_id(item) for item in result}
    duration = _safe_duration(segment)
    queries = _segment_fallback_queries(segment)

    for _ in range(max(1, MEDIA_SEARCH_ROUNDS)):
        for query in queries:
            fresh = search_new_broll(
                query,
                duration,
                exclude_ids=[item for item in exclude_ids if item],
                project_dir=project_dir,
            )
            for item in fresh:
                cid = _candidate_id(item)
                if not cid or cid in exclude_ids:
                    continue
                exclude_ids.add(cid)
                result.append(item)
                if len(result) >= target_count:
                    break
            if len(result) >= target_count:
                break
        if len(result) >= target_count:
            break

    result = _dedupe_candidates(result, limit=target_count)
    segment["main2_media_fallbacks"] = result
    segment["broll_candidates"] = result
    segment["broll_chosen"] = None


def _prepare_plan_media_fallbacks(plan: dict, project_dir: str):
    for segment in plan.get("segments", []):
        _enrich_segment_media_fallbacks(
            segment,
            project_dir=project_dir,
            target_count=FALLBACK_ALT_LIMIT,
        )


def _ordered_candidates_with_fallback(segment: dict) -> list[dict]:
    main2_list = segment.get("main2_media_fallbacks", [])
    if isinstance(main2_list, list) and main2_list:
        return _dedupe_candidates(main2_list, limit=FALLBACK_ALT_LIMIT)

    # main2 sengaja tidak mengandalkan pilihan AI; urutan fallback diambil dari kandidat search.
    candidates = _dedupe_candidates(segment.get("broll_candidates", []), limit=FALLBACK_ALT_LIMIT)
    if candidates:
        return candidates

    chosen = segment.get("broll_chosen")
    return [chosen] if isinstance(chosen, dict) else []


def _resolve_segment_video(segment: dict, project_dir: str, allow_download: bool) -> str | None:
    if not isinstance(segment, dict):
        return None

    ordered = _ordered_candidates_with_fallback(segment)
    if not ordered:
        return None

    for idx, candidate in enumerate(ordered):
        label = "media utama" if idx == 0 else f"fallback opsi {idx}"
        path = _resolve_candidate_existing_path(candidate, project_dir)
        if path and os.path.exists(path):
            segment["broll_chosen"] = candidate
            _log(f"Segmen {segment.get('id', '?')}: pakai {label} dari file lokal.")
            return os.path.abspath(path)

        if not allow_download:
            continue

        path = _download_candidate_to_download2(candidate, project_dir)
        if path and os.path.exists(path):
            segment["broll_chosen"] = candidate
            _log(f"Segmen {segment.get('id', '?')}: berhasil download {label} ke '{DOWNLOAD2_DIRNAME}'.")
            return os.path.abspath(path)
        _log(f"Segmen {segment.get('id', '?')}: gagal {label}, lanjut kandidat berikutnya.")

    return None


def _render_segment_cut_only(
    ffmpeg_exe: str,
    segment_video_path: str | None,
    output_path: str,
    duration: float,
    width: int,
    height: int,
    fps: int,
    bitrate: str,
    encoder: str,
):
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    fit_vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},format=yuv420p"
    )

    if segment_video_path and os.path.exists(segment_video_path):
        base_cmd = [
            ffmpeg_exe,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            segment_video_path,
            "-t",
            f"{duration:.3f}",
            "-vf",
            fit_vf,
            "-an",
        ]
        _run_encode_with_fallback(
            base_cmd=base_cmd,
            output_path=output_path,
            encoder=encoder,
            bitrate=bitrate,
            label=f"seg_{os.path.basename(output_path)}",
        )
        return

    base_cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r={fps}:d={duration:.3f}",
        "-vf",
        f"fps={fps},format=yuv420p",
        "-an",
    ]
    _run_encode_with_fallback(
        base_cmd=base_cmd,
        output_path=output_path,
        encoder=encoder,
        bitrate=bitrate,
        label=f"seg_fallback_{os.path.basename(output_path)}",
    )


def _write_concat_list(paths: list[str], list_path: str):
    with open(list_path, "w", encoding="utf-8") as fh:
        for item in paths:
            safe = os.path.abspath(item).replace("\\", "/").replace("'", "'\\''")
            fh.write(f"file '{safe}'\n")


def _concat_final(
    ffmpeg_exe: str,
    segment_files: list[str],
    audio_path: str | None,
    output_path: str,
):
    if not segment_files:
        raise RuntimeError("Tidak ada segmen yang berhasil dirender.")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    with tempfile.TemporaryDirectory(prefix="main2_concat_") as tmp:
        concat_txt = os.path.join(tmp, "segments.txt")
        _write_concat_list(segment_files, concat_txt)
        if audio_path and os.path.exists(audio_path):
            cmd = [
                ffmpeg_exe,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_txt,
                "-i",
                audio_path,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                output_path,
            ]
            _run_ffmpeg(cmd, label="concat_final_with_audio")
        else:
            cmd = [
                ffmpeg_exe,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_txt,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                output_path,
            ]
            _run_ffmpeg(cmd, label="concat_final_video_only")


def _load_project_bundle(project_input: str) -> tuple[str, dict, str | None, str | None]:
    project_input = os.path.abspath(project_input)
    cleanup_extract = None

    if os.path.isfile(project_input) and project_input.lower().endswith(".avep"):
        cleanup_extract = tempfile.mkdtemp(prefix="main2_avep_extract_")
        data = load_project(project_input, extract_to=cleanup_extract)
        project_dir = data.get("project_dir") or cleanup_extract
        default_output = os.path.join(
            os.path.dirname(project_input),
            f"{Path(project_input).stem}_final_fast.mp4",
        )
        return project_dir, data, default_output, cleanup_extract

    data = load_project(project_input)
    project_dir = data.get("project_dir") or os.path.abspath(project_input)
    project_paths = get_project_paths(project_dir)
    default_output = os.path.join(project_paths["exports"], "final_video_fast.mp4")
    return project_dir, data, default_output, cleanup_extract


def _load_plan_from_bundle(project_dir: str, data: dict) -> dict:
    plan = data.get("plan")
    if isinstance(plan, dict) and plan.get("segments"):
        return plan

    plan_path = get_project_paths(project_dir)["plan"]
    if not os.path.exists(plan_path):
        raise FileNotFoundError(f"Edit plan tidak ditemukan: {plan_path}")
    with open(plan_path, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    if not isinstance(loaded, dict) or not loaded.get("segments"):
        raise RuntimeError("File edit plan kosong atau tidak valid.")
    return loaded


def _write_json(path: str, payload: dict | list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def _build_plan_from_audio(project_dir: str, audio_path: str) -> dict:
    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError("Plan belum ada dan file voice over tidak ditemukan untuk auto-generate.")

    _log(f"Auto transkripsi audio dengan model {MAIN2_TRANSCRIBE_MODEL}...")
    segments, total_duration = transcribe(
        audio_path,
        log_cb=_log,
        model_override=MAIN2_TRANSCRIBE_MODEL,
    )
    save_transcript_cache(project_dir, audio_path, segments, total_duration)
    project_paths = get_project_paths(project_dir)
    _write_json(
        project_paths["transcript"],
        {
            "segments": segments,
            "total_duration": total_duration,
            "model": MAIN2_TRANSCRIBE_MODEL,
        },
    )

    _log("Membuat edit plan dari hasil transkripsi...")
    plan = generate_edit_plan(segments, total_duration, log_cb=_log)
    save_plan(plan, project_paths["plan"])

    _log("Mencari kandidat B-roll dari provider...")
    plan = fetch_candidates_for_plan(plan, project_dir=project_dir, log_cb=_log)
    _prepare_plan_media_fallbacks(plan, project_dir=project_dir)
    save_plan(plan, project_paths["plan"])
    _write_json(project_paths["search"], plan.get("segments", []))
    return plan


def _load_or_build_plan(project_dir: str, data: dict, audio_path: str, force_rebuild_plan: bool) -> dict:
    if not force_rebuild_plan:
        try:
            plan = _load_plan_from_bundle(project_dir, data)
            _prepare_plan_media_fallbacks(plan, project_dir=project_dir)
            return plan
        except Exception as exc:
            _log(f"Plan existing tidak siap ({exc}), lanjut auto-generate dari audio.")
    else:
        _log("Force rebuild aktif, generate ulang transkrip + edit plan.")

    return _build_plan_from_audio(project_dir, audio_path)


def render_project_fast(
    project_input: str,
    output_path: str | None = None,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
    fps: int = OUTPUT_FPS,
    bitrate: str = OUTPUT_BITRATE,
    allow_download: bool = True,
    force_rebuild_plan: bool = False,
    override_audio_path: str | None = None,
) -> str:
    project_dir, data, default_output, cleanup_extract = _load_project_bundle(project_input)
    temp_dir = tempfile.mkdtemp(prefix="main2_segments_")

    try:
        audio_path = (override_audio_path or "").strip() or data.get("audio_path") or get_project_paths(project_dir)["audio"]
        if audio_path and not os.path.exists(audio_path):
            _log("Voice over tidak ditemukan. Output akan video-only.")
            audio_path = None

        plan = _load_or_build_plan(
            project_dir=project_dir,
            data=data,
            audio_path=audio_path or "",
            force_rebuild_plan=force_rebuild_plan,
        )
        segments = plan.get("segments", [])
        if not segments:
            raise RuntimeError("Plan tidak punya segmen untuk dirender.")

        ffmpeg_exe = find_ffmpeg_executable()
        encoder_info = get_effective_video_encoder()
        encoder = encoder_info.get("effective", "libx264")
        _log(f"Project dir : {project_dir}")
        _log(f"FFmpeg      : {ffmpeg_exe}")
        _log(f"Encoder     : {encoder}")
        _log(f"Segmen      : {len(segments)}")
        _log(f"Download dir: {os.path.join(project_dir, DOWNLOAD2_DIRNAME)}")
        _log(
            f"Fallback    : {FALLBACK_ALT_LIMIT} kandidat media per segmen "
            "(non-AI choice, urutan fallback otomatis)"
        )

        out_path = os.path.abspath(output_path or default_output or "final_video_fast.mp4")
        seg_files: list[str] = []

        for idx, segment in enumerate(segments):
            wait_until_memory_below(
                limit_percent=90.0,
                resume_percent=84.0,
                check_interval=0.6,
                timeout=180.0,
                log_cb=_log,
            )
            duration = _safe_duration(segment)
            local_video = _resolve_segment_video(
                segment=segment,
                project_dir=project_dir,
                allow_download=allow_download,
            )
            seg_out = os.path.join(temp_dir, f"seg_{idx:03d}.mp4")
            _log(
                f"Render segmen {idx + 1}/{len(segments)} | durasi {duration:.2f}s | "
                f"sumber {'video' if local_video else 'fallback'}"
            )
            _render_segment_cut_only(
                ffmpeg_exe=ffmpeg_exe,
                segment_video_path=local_video,
                output_path=seg_out,
                duration=duration,
                width=int(width),
                height=int(height),
                fps=int(fps),
                bitrate=str(bitrate),
                encoder=encoder,
            )
            seg_files.append(seg_out)

        _log("Gabung semua segmen ke MP4 final...")
        _concat_final(
            ffmpeg_exe=ffmpeg_exe,
            segment_files=seg_files,
            audio_path=audio_path,
            output_path=out_path,
        )
        _log(f"Selesai. Output final: {out_path}")
        return out_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if cleanup_extract:
            shutil.rmtree(cleanup_extract, ignore_errors=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "main2.py - Render cepat dari proyek Auto Video Editor "
            "(cut + gabung saja, tanpa efek/transisi/subtitle/teks melayang)."
        )
    )
    parser.add_argument(
        "--project",
        default="",
        help="Path folder proyek ATAU file .avep",
    )
    parser.add_argument(
        "--audio",
        default="",
        help="Path file voice-over. Jika --project kosong, main2 otomatis bikin proyek baru dari audio ini.",
    )
    parser.add_argument(
        "--project-name",
        default="",
        help="Nama proyek baru saat pakai --audio tanpa --project. Default: nama file audio.",
    )
    parser.add_argument(
        "--projects-root",
        default="",
        help="Folder induk proyek saat auto-create dari --audio. Default: dari Settings.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Path output mp4 final (opsional). Default: final_video_fast.mp4 di folder exports proyek.",
    )
    parser.add_argument("--width", type=int, default=OUTPUT_WIDTH)
    parser.add_argument("--height", type=int, default=OUTPUT_HEIGHT)
    parser.add_argument("--fps", type=int, default=OUTPUT_FPS)
    parser.add_argument("--bitrate", default=OUTPUT_BITRATE)
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Jangan coba download B-roll yang hilang. Segmen kosong akan pakai fallback hitam.",
    )
    parser.add_argument(
        "--rebuild-plan",
        action="store_true",
        help=(
            "Paksa generate ulang transkripsi (Gemini 2.5 Flash) + edit plan + "
            f"{FALLBACK_ALT_LIMIT} fallback media per segmen."
        ),
    )
    return parser.parse_args()


def _default_project_name_from_audio(audio_path: str) -> str:
    stem = Path(audio_path).stem.strip()
    return stem or "New Project"


def _resolve_project_input(args: argparse.Namespace) -> str:
    project_arg = (args.project or "").strip()
    audio_arg = (args.audio or "").strip()
    project_name_arg = (args.project_name or "").strip()
    projects_root_arg = (args.projects_root or "").strip()

    if project_arg:
        if audio_arg and os.path.exists(project_arg) and os.path.isdir(project_arg):
            _log("Audio override terdeteksi. Menyalin voice-over ke folder proyek...")
            attach_voiceover(project_arg, audio_arg)
        return project_arg

    if audio_arg:
        if not os.path.exists(audio_arg):
            raise FileNotFoundError(f"File audio tidak ditemukan: {audio_arg}")
        name = project_name_arg or _default_project_name_from_audio(audio_arg)
        project_dir, _ = create_project(
            name=name,
            projects_root=projects_root_arg,
            voiceover_path=audio_arg,
        )
        _log(f"Proyek baru dibuat otomatis: {project_dir}")
        return project_dir

    print("Path proyek atau audio belum diisi.")
    print("Contoh cepat (auto bikin proyek dari audio):")
    print('  python main2.py --audio "C:\\Users\\...\\voice.mp3"')
    print("Contoh pakai proyek existing:")
    print('  python main2.py --project "C:\\Users\\...\\AutoVideoEditor Projects\\Nama Proyek"')
    try:
        typed = input("Masukkan path proyek (atau Enter untuk batal): ").strip()
    except EOFError:
        typed = ""
    if not typed:
        raise SystemExit(2)
    return typed


def main():
    args = _parse_args()
    project_input = _resolve_project_input(args)
    output = args.output.strip() or None
    audio_override = (args.audio or "").strip() or None
    result = render_project_fast(
        project_input=project_input,
        output_path=output,
        width=int(args.width),
        height=int(args.height),
        fps=int(args.fps),
        bitrate=str(args.bitrate),
        allow_download=not bool(args.no_download),
        force_rebuild_plan=bool(args.rebuild_plan),
        override_audio_path=audio_override,
    )
    print(result)


if __name__ == "__main__":
    main()
