"""
Video assembler — FFmpeg-native pipeline.

Perubahan utama vs versi lama:
  1. render_full  : setiap segmen ditulis ke temp .mp4 → RAM hanya 1 segmen
  2. Efek & grade : FFmpeg filtergraph (zoompan, curves) — GPU aktif
  3. Encoder      : h264_qsv (Intel GPU) dengan fallback libx264
  4. Concat final : ffmpeg concat demuxer → tidak ada MoviePy concatenate
  5. Preview      : tetap MoviePy (ringan, 360p, simplify_visuals=True)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from copy import deepcopy

import numpy as np

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

from config import OUTPUT_BITRATE, OUTPUT_FPS, OUTPUT_HEIGHT, OUTPUT_PRESET, OUTPUT_WIDTH
from core.asset_manager import resolve_project_path
from core.broll_fetcher import ensure_segment_video_available
from core.effects import (
    apply_transitions,
    get_effect_filter,
    get_transition_filters,
)
from core.floating_text import make_floating_text_overlay
from core.moviepy_compat import patch_moviepy
from core.resource_guard import wait_until_memory_below
from core.video_encoder_manager import find_ffmpeg_executable, get_effective_video_encoder

patch_moviepy()

# ── Profil render ─────────────────────────────────────────────────────────────

FINAL_RENDER_PROFILE = {
    "name": "final",
    "width": OUTPUT_WIDTH,
    "height": OUTPUT_HEIGHT,
    "fps": OUTPUT_FPS,
    "bitrate": OUTPUT_BITRATE,
    "preset": OUTPUT_PRESET,
    "threads": 2,          # N5100: 2 thread cukup, sisanya buat GPU
    "simplify_visuals": False,
}

PREVIEW_RENDER_PROFILE = {
    "name": "preview",
    "width": 640,
    "height": 360,
    "fps": 15,
    "bitrate": "900k",
    "preset": "ultrafast",
    "threads": 1,
    "simplify_visuals": True,
}

SUBTITLE_STYLES = {
    "clean":         {"font_size": 42, "color": "white",   "stroke_color": "black",   "stroke_width": 2, "bottom_offset": 190, "fade": 0.15},
    "bold":          {"font_size": 50, "color": "#f8fafc", "stroke_color": "#020617", "stroke_width": 3, "bottom_offset": 198, "fade": 0.18},
    "minimal":       {"font_size": 34, "color": "#e2e8f0", "stroke_color": "#0f172a", "stroke_width": 1, "bottom_offset": 160, "fade": 0.12},
    "high_contrast": {"font_size": 44, "color": "#fefce8", "stroke_color": "black",   "stroke_width": 4, "bottom_offset": 194, "fade": 0.15},
}

_PREVIEW_EFFECT_FALLBACKS = {
    "handheld_shake": "static",
    "whip_pan": "static",
    "slow_zoom_punch": "ken_burns_zoom_in",
}
_PREVIEW_TRANSITION_FALLBACKS = {
    "glitch": "cut",
    "zoom_blur": "fade",
    "wipe_left": "fade",
    "dip_to_white": "fade",
}
_VF_VALIDATION_CACHE: dict[tuple[int, int, int, str], tuple[bool, str]] = {}


def get_render_profile(kind: str = "final") -> dict:
    base = PREVIEW_RENDER_PROFILE if kind == "preview" else FINAL_RENDER_PROFILE
    return deepcopy(base)


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def render_full(
    plan: dict,
    audio_path: str,
    output_path: str,
    progress_cb=None,
    download_cb=None,
) -> str:
    """
    Final render: setiap segmen → temp .mp4 → FFmpeg concat + audio mix.
    RAM yang dipakai = 1 segmen sekaligus, bukan seluruh video.
    """
    if not isinstance(plan, dict) or not plan.get("segments"):
        raise RuntimeError("Edit plan kosong atau tidak valid.")
    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError("File audio untuk render tidak ditemukan.")

    profile = get_render_profile("final")
    project_dir = os.path.abspath(os.path.join(os.path.dirname(output_path), os.pardir))
    segments = plan["segments"]
    total = len(segments)

    # Deteksi encoder sekali di awal
    encoder_info = get_effective_video_encoder()
    encoder = encoder_info.get("effective", "libx264")
    ffmpeg_exe = find_ffmpeg_executable()
    print(f"[Renderer] Encoder: {encoder} | FFmpeg: {ffmpeg_exe}")

    temp_dir = tempfile.mkdtemp(prefix="ave_render_")
    seg_files: list[str] = []

    try:
        # ── 1. Render setiap segmen ke temp file ──────────────────────────────
        for i, seg in enumerate(segments):
            if progress_cb:
                progress_cb(i, total, f"Render segmen {i + 1}/{total}...")

            wait_until_memory_below(limit_percent=88.0, resume_percent=82.0,
                                    check_interval=0.75, timeout=120.0, log_cb=print)

            seg_out = os.path.join(temp_dir, f"seg_{i:03d}.mp4")
            _render_segment_to_file(
                seg,
                output_path=seg_out,
                plan=plan,
                project_dir=project_dir,
                profile=profile,
                encoder=encoder,
                ffmpeg_exe=ffmpeg_exe,
                download_cb=download_cb,
            )
            seg_files.append(seg_out)

        # ── 2. Concat intro + segmen + outro ──────────────────────────────────
        if progress_cb:
            progress_cb(total, total, "Menggabungkan semua segmen...")

        concat_list_path = os.path.join(temp_dir, "concat.txt")
        all_files: list[str] = []

        intro_path = _get_asset_path(plan, project_dir, "intro_video")
        if intro_path:
            all_files.append(intro_path)
        all_files.extend(seg_files)
        outro_path = _get_asset_path(plan, project_dir, "outro_video")
        if outro_path:
            all_files.append(outro_path)

        with open(concat_list_path, "w", encoding="utf-8") as fh:
            for p in all_files:
                fh.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")

        if progress_cb:
            progress_cb(total, total, "Exporting video final...")

        _ffmpeg_concat_with_audio(
            concat_list_path=concat_list_path,
            audio_path=audio_path,
            output_path=output_path,
            profile=profile,
            encoder=encoder,
            ffmpeg_exe=ffmpeg_exe,
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path


def render_segment_preview(
    segment: dict,
    output_path: str,
    plan: dict = None,
    output_dir: str = "",
    download_cb=None,
) -> str:
    """Preview render per segmen — tetap pakai MoviePy, 360p, ringan."""
    profile = get_render_profile("preview")
    clip = _render_segment_moviepy(
        segment,
        plan=plan,
        output_dir=output_dir,
        download_cb=download_cb,
        profile=profile,
    )
    try:
        _write_moviepy_clip(clip, output_path, profile, include_audio=False)
    finally:
        try:
            clip.close()
        except Exception:
            pass
    return output_path


def build_preview_draft(
    plan: dict,
    audio_path: str,
    chunk_paths: list[str],
    output_path: str,
    output_dir: str = "",
    ready_segments: int = 0,
) -> str:
    """Gabungkan chunk preview yang sudah ada ke satu draft mp4."""
    profile = get_render_profile("preview")
    chunk_clips = []
    intro_clip = outro_clip = voice_audio = main_video = final_video = None

    try:
        for path in chunk_paths:
            if path and os.path.exists(path):
                chunk_clips.append(VideoFileClip(path, audio=False))

        intro_clip = _load_project_video_moviepy(plan, output_dir, "intro_video", profile)
        total_segments = len(plan.get("segments", [])) if isinstance(plan, dict) else 0
        if ready_segments >= total_segments > 0:
            outro_clip = _load_project_video_moviepy(plan, output_dir, "outro_video", profile)

        parts = []
        if intro_clip:
            parts.append(intro_clip)
        if chunk_clips:
            main_video = concatenate_videoclips(chunk_clips, method="compose")
            if audio_path and os.path.exists(audio_path):
                voice_audio = AudioFileClip(audio_path)
                dur = min(float(voice_audio.duration or 0), float(main_video.duration or 0))
                if dur > 0:
                    main_video = main_video.set_audio(voice_audio.subclip(0, dur))
            parts.append(main_video)
        if outro_clip:
            parts.append(outro_clip)

        if not parts:
            return ""

        final_video = concatenate_videoclips(parts, method="compose") if len(parts) > 1 else parts[0]
        _write_moviepy_clip(final_video, output_path, profile, include_audio=voice_audio is not None)
        return output_path
    finally:
        for c in chunk_clips:
            _safe_close(c)
        for c in (intro_clip, outro_clip, main_video, final_video, voice_audio):
            _safe_close(c)


# ══════════════════════════════════════════════════════════════════════════════
#  INTERNAL — FFmpeg-native render per segmen
# ══════════════════════════════════════════════════════════════════════════════

def _render_segment_to_file(
    segment: dict,
    output_path: str,
    plan: dict,
    project_dir: str,
    profile: dict,
    encoder: str,
    ffmpeg_exe: str,
    download_cb=None,
):
    """
    Render satu segmen ke file MP4 menggunakan FFmpeg filtergraph penuh.
    Tidak ada MoviePy, tidak ada numpy per-frame.
    """
    w = int(profile["width"])
    h = int(profile["height"])
    fps = int(profile["fps"])
    bitrate = profile["bitrate"]
    seg_duration = float(segment.get("render_duration") or 0)
    if seg_duration <= 0:
        seg_duration = max(1.0, float(segment.get("end", 0)) - float(segment.get("start", 0)))

    # Pastikan video B-roll tersedia
    local_path = ensure_segment_video_available(
        segment,
        project_dir=project_dir,
        progress_cb=download_cb,
        log_cb=print,
    )

    effect_name   = str(segment.get("effect", "static") or "static")
    grade_name    = str(segment.get("color_grade", "neutral") or "neutral")
    trans_in      = str(segment.get("transition_in", "cut") or "cut")
    trans_out     = str(segment.get("transition_out", "cut") or "cut")

    effect_f = get_effect_filter(effect_name, seg_duration, w, h, fps)
    # Color grading dinonaktifkan untuk stabilitas render di perangkat low-spec.
    # Field tetap dibaca demi kompatibilitas data plan lama.
    _ = grade_name
    grade_f = ""
    fi, fo   = get_transition_filters(trans_in, trans_out, seg_duration, fps)

    # Susun filtergraph: efek → grade → fade_in → fade_out
    parts = [f for f in [effect_f, grade_f, fi, fo] if f]
    vf = ",".join(parts) if parts else f"scale={w}:{h},fps={fps}"

    # Tambah overlay teks jika ada (lewat drawtext FFmpeg)
    project_settings = plan.get("project_settings", {}) if isinstance(plan, dict) else {}
    emphasis = segment.get("emphasis_text")
    text_f = ""
    if emphasis and _is_segment_floating_text_enabled(segment, project_settings):
        text_f = _build_drawtext_filter(emphasis, w, h, seg_duration, project_settings) or ""
    if text_f:
        vf += f",{text_f}"

    vf = _choose_safe_segment_vf(
        vf=vf,
        w=w,
        h=h,
        fps=fps,
        ffmpeg_exe=ffmpeg_exe,
        seg_label=f"seg_{segment.get('id', '?')}",
    )

    if local_path and os.path.exists(local_path):
        try:
            _ffmpeg_render_from_video(
                input_path=local_path,
                output_path=output_path,
                vf=vf,
                duration=seg_duration,
                w=w, h=h, fps=fps,
                bitrate=bitrate,
                encoder=encoder,
                ffmpeg_exe=ffmpeg_exe,
            )
        except Exception as exc:
            print(f"[Renderer] Seg {segment.get('id', '?')}: vf utama gagal, retry aman. Detail: {exc}")
            safe_vf = f"scale={w}:{h},fps={fps}"
            try:
                _ffmpeg_render_from_video(
                    input_path=local_path,
                    output_path=output_path,
                    vf=safe_vf,
                    duration=seg_duration,
                    w=w, h=h, fps=fps,
                    bitrate=bitrate,
                    encoder=encoder,
                    ffmpeg_exe=ffmpeg_exe,
                )
            except Exception as fallback_exc:
                print(
                    f"[Renderer] Seg {segment.get('id', '?')}: retry aman gagal, "
                    f"pakai fallback warna. Detail: {fallback_exc}"
                )
                _ffmpeg_render_color(
                    output_path=output_path,
                    duration=seg_duration,
                    w=w, h=h, fps=fps,
                    bitrate=bitrate,
                    encoder=encoder,
                    ffmpeg_exe=ffmpeg_exe,
                    vf="",
                )
    else:
        # Fallback: color clip hitam
        print(f"[Renderer] Seg {segment.get('id', '?')}: B-roll tidak tersedia, pakai fallback.")
        _ffmpeg_render_color(
            output_path=output_path,
            duration=seg_duration,
            w=w, h=h, fps=fps,
            bitrate=bitrate,
            encoder=encoder,
            ffmpeg_exe=ffmpeg_exe,
            vf=vf,
        )


def _ensure_scale_fps(vf: str, w: int, h: int, fps: int) -> str:
    result = str(vf or "").strip()
    if not result:
        result = f"scale={w}:{h},fps={fps}"
    if f"scale={w}:{h}" not in result and f"s={w}x{h}" not in result:
        result = f"{result},scale={w}:{h}"
    if f"fps={fps}" not in result:
        result = f"{result},fps={fps}"
    return result


def _probe_filtergraph(vf: str, w: int, h: int, fps: int, ffmpeg_exe: str) -> tuple[bool, str]:
    normalized = _ensure_scale_fps(vf, w, h, fps)
    key = (w, h, fps, normalized)
    cached = _VF_VALIDATION_CACHE.get(key)
    if cached is not None:
        return cached

    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={w}x{h}:r={fps}:d=0.20",
        "-vf",
        normalized,
        "-frames:v",
        "1",
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=20,
        )
        ok = proc.returncode == 0
        detail = ((proc.stderr or proc.stdout or "").strip())[:280]
    except Exception as exc:
        ok = False
        detail = str(exc)[:280]

    _VF_VALIDATION_CACHE[key] = (ok, detail)
    return ok, detail


def _choose_safe_segment_vf(
    vf: str,
    w: int,
    h: int,
    fps: int,
    ffmpeg_exe: str,
    seg_label: str = "",
) -> str:
    base = _ensure_scale_fps(vf, w, h, fps)
    minimal = f"scale={w}:{h},fps={fps}"
    candidates = [base]
    if base != minimal:
        candidates.append(minimal)

    for idx, candidate in enumerate(candidates):
        ok, detail = _probe_filtergraph(candidate, w, h, fps, ffmpeg_exe)
        if ok:
            if idx > 0:
                print(
                    f"[Renderer] {seg_label}: filter kompleks tidak valid, "
                    "otomatis pakai filter minimal agar render lanjut."
                )
            return candidate
        if detail:
            print(f"[Renderer] {seg_label}: filter candidate {idx + 1} invalid: {detail}")

    return minimal


def _ffmpeg_render_from_video(
    input_path: str,
    output_path: str,
    vf: str,
    duration: float,
    w: int, h: int, fps: int,
    bitrate: str,
    encoder: str,
    ffmpeg_exe: str,
):
    """Render video B-roll → segmen mp4 dengan filtergraph."""
    if os.path.exists(output_path):
        os.remove(output_path)

    base_cmd = [
        ffmpeg_exe,
        "-y",
        "-stream_loop", "-1",     # loop jika video lebih pendek dari durasi
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-an",                    # audio ditambah nanti saat concat
    ]
    _run_encode_with_fallback(
        base_cmd=base_cmd,
        output_path=output_path,
        encoder=encoder,
        bitrate=bitrate,
        label=f"render_seg {os.path.basename(output_path)}",
    )


def _ffmpeg_render_color(
    output_path: str,
    duration: float,
    w: int, h: int, fps: int,
    bitrate: str,
    encoder: str,
    ffmpeg_exe: str,
    vf: str = "",
):
    """Buat klip warna solid hitam sebagai fallback."""
    if os.path.exists(output_path):
        os.remove(output_path)

    # Mulai dari color source, lalu apply grade/transition jika ada
    grade_part = ",".join(p for p in [vf] if p and "zoompan" not in p and "scale=8000" not in p)
    base_vf = f"scale={w}:{h},fps={fps}"
    if grade_part:
        base_vf += "," + grade_part

    base_cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={w}x{h}:r={fps}:d={duration:.3f}",
        "-vf", base_vf,
        "-an",
    ]
    _run_encode_with_fallback(
        base_cmd=base_cmd,
        output_path=output_path,
        encoder=encoder,
        bitrate=bitrate,
        label="render_fallback",
    )


def _ffmpeg_concat_with_audio(
    concat_list_path: str,
    audio_path: str,
    output_path: str,
    profile: dict,
    encoder: str,
    ffmpeg_exe: str,
):
    """
    Gabungkan semua segmen + audio menggunakan FFmpeg concat demuxer.
    Tidak ada re-encode video (stream copy), hanya audio di-encode ke AAC.
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",           # stream copy — tidak re-encode video
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    _run_ffmpeg(cmd, label="concat_final")


def _encoder_args(encoder: str, bitrate: str) -> list[str]:
    """Return FFmpeg codec args untuk encoder yang dipilih."""
    if encoder == "h264_qsv":
        return [
            "-c:v", "h264_qsv",
            "-b:v", bitrate,
            "-look_ahead", "0",   # latency rendah, cocok N5100
            "-async_depth", "1",
        ]
    # libx264 fallback
    return [
        "-c:v", "libx264",
        "-b:v", bitrate,
        "-preset", "ultrafast",   # final render sudah dapat kualitas dari bitrate
        "-pix_fmt", "yuv420p",
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
    except RuntimeError as exc:
        if encoder != "h264_qsv":
            raise
        print(f"[Renderer] {label}: h264_qsv gagal, fallback ke libx264. Detail: {exc}")

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    fallback_cmd = [*base_cmd, *_encoder_args("libx264", bitrate), "-movflags", "+faststart", output_path]
    _run_ffmpeg(fallback_cmd, label=f"{label} fallback_libx264")


def _run_ffmpeg(cmd: list[str], label: str = "ffmpeg"):
    """Jalankan FFmpeg subprocess, raise RuntimeError kalau gagal."""
    print(f"[Renderer:{label}] {' '.join(cmd[:6])}...")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if result.returncode != 0:
        stderr = (result.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg [{label}] gagal (code {result.returncode}):\n{stderr}")


# ══════════════════════════════════════════════════════════════════════════════
#  INTERNAL — MoviePy path (preview render saja)
# ══════════════════════════════════════════════════════════════════════════════

def _render_segment_moviepy(
    segment: dict,
    plan: dict = None,
    output_dir: str = "",
    download_cb=None,
    profile: dict = None,
):
    """MoviePy render untuk preview 360p — simplify_visuals=True."""
    profile = profile or get_render_profile("preview")
    render_w = int(profile["width"])
    render_h = int(profile["height"])
    seg_duration = float(segment.get("render_duration") or 0)
    if seg_duration <= 0:
        seg_duration = max(1.0, float(segment.get("end", 0)) - float(segment.get("start", 0)))

    local_path = ensure_segment_video_available(
        segment,
        project_dir=output_dir,
        progress_cb=download_cb,
        log_cb=print,
    )

    if local_path and os.path.exists(local_path):
        try:
            broll_clip = VideoFileClip(local_path, audio=False)
        except Exception as exc:
            print(f"[Renderer] Load preview clip gagal: {exc}")
            broll_clip = None
    else:
        broll_clip = None

    if broll_clip is None:
        broll_clip = _create_fallback_clip(seg_duration, segment.get("id", "?"), (render_w, render_h))

    broll_clip = _ensure_clip_duration(broll_clip, seg_duration, segment.get("id", "?"), (render_w, render_h))
    broll_clip = _fit_to_canvas_safe(broll_clip, render_w, render_h, segment.get("id", "?"))

    # Preview: hanya transisi ringan (fade), tidak ada efek berat
    trans_in  = _normalize_transition(segment.get("transition_in", "cut"), profile)
    trans_out = _normalize_transition(segment.get("transition_out", "cut"), profile)
    broll_clip = apply_transitions(broll_clip, trans_in, trans_out)

    layers = [broll_clip]
    project_settings = plan.get("project_settings", {}) if isinstance(plan, dict) else {}

    emphasis = segment.get("emphasis_text")
    if emphasis and _is_segment_floating_text_enabled(segment, project_settings):
        try:
            start_offset = min(0.9, seg_duration * 0.08)
            emp_dur = max(seg_duration * 0.82, seg_duration - 0.75) - start_offset
            if emp_dur > 0.5:
                emp_clip = make_floating_text_overlay(
                    text=emphasis,
                    duration=emp_dur,
                    size=(render_w, render_h),
                    style=_resolve_floating_text_style(project_settings, profile),
                ).set_start(start_offset)
                layers.append(emp_clip)
        except Exception as exc:
            print(f"[Renderer] Emphasis preview error: {exc}")

    if bool(project_settings.get("subtitle_enabled", False)):
        sub_clip = _make_subtitle_overlay(
            segment.get("subtitle_text") or segment.get("transcript", ""),
            seg_duration,
            project_settings.get("subtitle_style", "clean"),
            size=(render_w, render_h),
        )
        if sub_clip:
            layers.append(sub_clip)

    try:
        return CompositeVideoClip(layers, size=(render_w, render_h)).set_duration(seg_duration)
    except Exception:
        return broll_clip.set_duration(seg_duration)


def _write_moviepy_clip(clip, output_path: str, profile: dict, include_audio: bool):
    """Tulis clip MoviePy ke file — dipakai untuk preview saja."""
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass
    kwargs: dict = {
        "fps": profile["fps"],
        "codec": "libx264",
        "bitrate": profile["bitrate"],
        "preset": profile.get("preset", "ultrafast"),
        "threads": int(profile.get("threads", 1)),
        "logger": None,
        "ffmpeg_params": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    }
    if include_audio:
        kwargs["audio_codec"] = "aac"
    else:
        kwargs["audio"] = False
    clip.write_videofile(output_path, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _build_drawtext_filter(text: str, w: int, h: int, duration: float, project_settings: dict) -> str:
    """FFmpeg drawtext filter untuk emphasis overlay."""
    safe_text = (text or "").replace("'", "\\'").replace(":", "\\:").replace("\\n", " ")[:120]
    font_size = int(project_settings.get("floating_text_size", 58) or 58)
    font_size = max(20, min(font_size, 96))
    y_pos = int(h * 0.18)
    fade_dur = min(0.25, duration * 0.15)
    alpha_expr = (
        f"if(lt(t\\,{fade_dur:.2f})\\,t/{fade_dur:.2f}\\,"
        f"if(gt(t\\,{duration-fade_dur:.2f})\\,"
        f"({duration:.2f}-t)/{fade_dur:.2f}\\,1))"
    )
    return (
        f"drawtext=text='{safe_text}'"
        f":fontsize={font_size}"
        f":fontcolor=white"
        f":borderw=2"
        f":bordercolor=black"
        f":x=(w-text_w)/2"
        f":y={y_pos}"
        f":alpha='{alpha_expr}'"
    )


def _get_asset_path(plan: dict, project_dir: str, key: str) -> str | None:
    asset = plan.get("project_settings", {}).get(key)
    if not isinstance(asset, dict):
        return None
    path = resolve_project_path(
        asset.get("absolute_path"),
        project_dir,
        asset.get("relative_path"),
    )
    return path if path and os.path.exists(path) else None


def _load_project_video_moviepy(plan: dict, output_dir: str, key: str, profile: dict):
    path = _get_asset_path(plan, output_dir, key)
    if not path:
        return None
    try:
        clip = VideoFileClip(path, audio=False)
        return _fit_to_canvas(clip, profile["width"], profile["height"])
    except Exception as exc:
        print(f"[Renderer] Load {key} gagal: {exc}")
        return None


def _is_segment_floating_text_enabled(segment: dict, project_settings: dict) -> bool:
    mode = str(segment.get("floating_text_mode", "inherit") or "inherit").strip().lower()
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    return bool(project_settings.get("floating_text_enabled", False))


def _resolve_floating_text_style(project_settings: dict, profile: dict) -> dict:
    scale = profile["height"] / max(OUTPUT_HEIGHT, 1)
    return {
        "font": project_settings.get("floating_text_font", "Segoe UI"),
        "font_size": max(20, int(float(project_settings.get("floating_text_size", 58) or 58) * max(scale, 0.55))),
        "animation": project_settings.get("floating_text_animation", "slide_up"),
        "position": project_settings.get("floating_text_position", "upper_third"),
    }


def _make_subtitle_overlay(text: str, duration: float, style_name: str = "clean", size: tuple = None):
    text = (text or "").strip()
    if not text:
        return None
    render_w, render_h = size or (OUTPUT_WIDTH, OUTPUT_HEIGHT)
    scale = render_h / max(OUTPUT_HEIGHT, 1)
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["clean"])
    try:
        sub = TextClip(
            text=text,
            font_size=max(20, int(style["font_size"] * max(scale, 0.55))),
            font=None,
            color=style["color"],
            stroke_color=style["stroke_color"],
            stroke_width=max(1, int(style["stroke_width"] * max(scale, 0.7))),
            method="caption",
            size=(render_w - max(120, int(180 * max(scale, 0.6))), None),
            text_align="center",
            horizontal_align="center",
            duration=duration,
        )
        bottom_offset = max(42, int(style["bottom_offset"] * max(scale, 0.55)))
        sub = sub.set_position(("center", render_h - bottom_offset))
        return sub.fadein(style["fade"]).fadeout(style["fade"])
    except Exception as exc:
        print(f"[Renderer] Subtitle error: {exc}")
        return None


def _create_fallback_clip(duration: float, segment_id, size: tuple):
    w, h = size
    try:
        return ColorClip(size=(w, h), color=(10, 10, 20)).set_duration(duration)
    except Exception:
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (10, 10, 20)
        return ImageClip(frame).set_duration(duration)


def _ensure_clip_duration(clip, seg_duration: float, segment_id, size: tuple):
    try:
        clip_dur = float(getattr(clip, "duration", 0) or 0)
        if clip_dur <= 0:
            return _create_fallback_clip(seg_duration, segment_id, size)
        if clip_dur < seg_duration:
            loops = int(seg_duration / max(clip_dur, 0.1)) + 2
            clip = concatenate_videoclips([clip] * loops, method="compose")
        return clip.subclip(0, seg_duration)
    except Exception as exc:
        print(f"[Renderer] ensure_clip_duration error seg {segment_id}: {exc}")
        return _create_fallback_clip(seg_duration, segment_id, size)


def _fit_to_canvas_safe(clip, w: int, h: int, segment_id):
    try:
        return _fit_to_canvas(clip, w, h)
    except Exception as exc:
        print(f"[Renderer] fit_to_canvas gagal seg {segment_id}: {exc}")
        return clip


def _fit_to_canvas(clip, target_w: int, target_h: int):
    src_w, src_h = clip.size
    src_ratio = src_w / src_h
    tgt_ratio = target_w / target_h
    if src_ratio > tgt_ratio:
        clip = clip.resize(height=target_h)
    else:
        clip = clip.resize(width=target_w)
    cw, ch = clip.size
    x1 = (cw - target_w) // 2
    y1 = (ch - target_h) // 2
    return clip.crop(x1=x1, y1=y1, width=target_w, height=target_h)


def _normalize_transition(name: str, profile: dict) -> str:
    name = str(name or "cut")
    if profile.get("simplify_visuals"):
        return _PREVIEW_TRANSITION_FALLBACKS.get(name, name)
    return name


def _safe_close(clip):
    try:
        if clip is not None:
            clip.close()
    except Exception:
        pass
