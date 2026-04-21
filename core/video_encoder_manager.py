"""
Helpers for detecting and selecting the safest available H.264 encoder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

_SUPPORTED_ENCODERS = ("h264_qsv", "libx264")


def normalize_encoder_mode(mode: str | None) -> str:
    value = str(mode or "auto").strip().lower()
    if value in {"auto", "h264_qsv", "libx264"}:
        return value
    return "auto"


def find_ffmpeg_executable() -> str:
    env_path = os.environ.get("IMAGEIO_FFMPEG_EXE", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path

    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.exists(bundled):
            return bundled
    except Exception:
        pass

    return "ffmpeg"


def _run_ffmpeg(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    command = [find_ffmpeg_executable(), *args]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,
    )


def list_ffmpeg_encoders() -> tuple[set[str], str]:
    try:
        proc = _run_ffmpeg(["-hide_banner", "-encoders"], timeout=30)
    except Exception as exc:
        return set(), f"Gagal menjalankan FFmpeg: {exc}"

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        return set(), f"FFmpeg error saat membaca daftar encoder: {stderr[:180] or '-'}"

    encoders: set[str] = set()
    pattern = re.compile(r"^\s*[A-Z\.]{6}\s+([a-z0-9_]+)\s", re.IGNORECASE)
    for line in proc.stdout.splitlines():
        match = pattern.match(line)
        if match:
            encoders.add(match.group(1).lower())
    return encoders, ""


def probe_h264_qsv(encoders: set[str] | None = None) -> tuple[bool, str]:
    encoders = encoders or set()
    if encoders and "h264_qsv" not in encoders:
        return False, "Encoder h264_qsv tidak tersedia di build FFmpeg ini."

    try:
        proc = _run_ffmpeg(
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=128x72:d=0.3",
                "-frames:v",
                "1",
                "-an",
                "-c:v",
                "h264_qsv",
                "-f",
                "null",
                "-",
            ],
            timeout=40,
        )
    except Exception as exc:
        return False, f"Probe h264_qsv gagal dijalankan: {exc}"

    if proc.returncode == 0:
        return True, "Intel Quick Sync terdeteksi dan siap dipakai."

    detail = (proc.stderr or proc.stdout or "").strip()
    if not detail:
        detail = "Probe selesai tetapi h264_qsv tidak bisa dipakai di perangkat ini."
    return False, detail[:220]


def _detect_best_encoder() -> dict:
    ffmpeg_path = find_ffmpeg_executable()
    encoders, error = list_ffmpeg_encoders()
    available = [name for name in _SUPPORTED_ENCODERS if name in encoders]

    if error:
        return {
            "ffmpeg_path": ffmpeg_path,
            "available": available,
            "detected": "libx264",
            "status": error,
            "checked_at": int(time.time()),
        }

    qsv_ok, qsv_status = probe_h264_qsv(encoders)
    if qsv_ok:
        status = f"Deteksi otomatis memilih h264_qsv. {qsv_status}"
        return {
            "ffmpeg_path": ffmpeg_path,
            "available": available or list(_SUPPORTED_ENCODERS),
            "detected": "h264_qsv",
            "status": status,
            "checked_at": int(time.time()),
        }

    if "libx264" in encoders:
        status = (
            "Deteksi otomatis memilih libx264 karena Intel Quick Sync belum siap. "
            f"Detail: {qsv_status}"
        )
        return {
            "ffmpeg_path": ffmpeg_path,
            "available": available or ["libx264"],
            "detected": "libx264",
            "status": status,
            "checked_at": int(time.time()),
        }

    fallback_status = (
        "FFmpeg terdeteksi tetapi encoder H.264 standar tidak ditemukan. "
        f"Detail: {qsv_status}"
    )
    return {
        "ffmpeg_path": ffmpeg_path,
        "available": available,
        "detected": "",
        "status": fallback_status,
        "checked_at": int(time.time()),
    }


def refresh_video_encoder_detection(force: bool = False) -> dict:
    from core.settings_manager import settings

    cached = settings.get_video_encoder_detection()
    if (
        not force
        and cached.get("checked_at")
        and cached.get("detected")
        and cached.get("status")
    ):
        return {
            "ffmpeg_path": find_ffmpeg_executable(),
            "available": [],
            **cached,
        }

    result = _detect_best_encoder()
    settings.set_many(
        {
            "detected_video_encoder": result.get("detected", ""),
            "detected_video_encoder_status": result.get("status", "Belum dicek"),
            "detected_video_encoder_checked_at": int(result.get("checked_at", 0) or 0),
        }
    )
    return result


def get_effective_video_encoder(
    requested_mode: str | None = None,
    force_refresh: bool = False,
) -> dict:
    from core.settings_manager import settings

    mode = normalize_encoder_mode(requested_mode or settings.get_video_encoder_mode())
    detection = refresh_video_encoder_detection(force=force_refresh)
    detected = str(detection.get("detected", "") or "").strip().lower()
    base_status = str(detection.get("status", "") or "").strip()

    if mode == "auto":
        effective = detected or "libx264"
        status = (
            f"Mode otomatis aktif. Encoder yang dipakai: {effective}. {base_status}"
            if base_status
            else f"Mode otomatis aktif. Encoder yang dipakai: {effective}."
        )
        return {
            "mode": mode,
            "effective": effective,
            "detected": detected,
            "status": status,
            "checked_at": int(detection.get("checked_at", 0) or 0),
            "ffmpeg_path": detection.get("ffmpeg_path", find_ffmpeg_executable()),
        }

    if mode == "h264_qsv":
        if detected == "h264_qsv":
            return {
                "mode": mode,
                "effective": "h264_qsv",
                "detected": detected,
                "status": "Mode manual h264_qsv aktif. Intel Quick Sync siap dipakai.",
                "checked_at": int(detection.get("checked_at", 0) or 0),
                "ffmpeg_path": detection.get("ffmpeg_path", find_ffmpeg_executable()),
            }
        return {
            "mode": mode,
            "effective": "libx264",
            "detected": detected,
            "status": (
                "Mode manual h264_qsv dipilih, tetapi perangkat/driver belum siap. "
                "Render akan fallback ke libx264. "
                f"{base_status}"
            ).strip(),
            "checked_at": int(detection.get("checked_at", 0) or 0),
            "ffmpeg_path": detection.get("ffmpeg_path", find_ffmpeg_executable()),
        }

    return {
        "mode": mode,
        "effective": "libx264",
        "detected": detected,
        "status": "Mode manual libx264 aktif. Render memakai encoder CPU yang paling aman.",
        "checked_at": int(detection.get("checked_at", 0) or 0),
        "ffmpeg_path": detection.get("ffmpeg_path", find_ffmpeg_executable()),
    }


def get_moviepy_write_options(
    requested_mode: str | None = None,
    force_refresh: bool = False,
) -> tuple[dict, dict]:
    info = get_effective_video_encoder(
        requested_mode=requested_mode,
        force_refresh=force_refresh,
    )

    ffmpeg_params = ["-movflags", "+faststart"]
    if info["effective"] == "libx264":
        ffmpeg_params = ["-pix_fmt", "yuv420p", *ffmpeg_params]
    elif info["effective"] == "h264_qsv":
        ffmpeg_params = ["-look_ahead", "0", *ffmpeg_params]

    return info, {
        "codec": info["effective"] or "libx264",
        "ffmpeg_params": ffmpeg_params,
    }
