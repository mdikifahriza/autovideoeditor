# ─────────────────────────────────────────────
#  core/effects.py  —  FFmpeg-native Effects & Color Grades
# ─────────────────────────────────────────────
"""
Semua efek, color grade, dan transisi dikembalikan sebagai
FFmpeg filtergraph string — bukan Python frame-loop.

Pipeline baru:
  FFmpeg decode → vf filtergraph → h264_qsv/libx264 encode
  (tidak ada PIL, tidak ada numpy per-frame, GPU aktif penuh)
"""

from __future__ import annotations


# ══════════════════════════════════════════════════════════════════════════════
#  EFFECTS — mengembalikan vf string untuk satu klip
# ══════════════════════════════════════════════════════════════════════════════

def effect_ken_burns_zoom_in(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='min(zoom+0.0010,1.10)'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_ken_burns_zoom_out(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='if(eq(on\\,1)\\,1.10\\,max(zoom-0.0010\\,1.00))'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_slow_pan_left(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    pan_px = int(w * 0.06)
    return (
        f"scale={w + pan_px}:{h},"
        f"zoompan=z='1':x='on/{frames}*{pan_px}':y='0'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_slow_pan_right(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    pan_px = int(w * 0.06)
    return (
        f"scale={w + pan_px}:{h},"
        f"zoompan=z='1':x='{pan_px}-(on/{frames}*{pan_px})':y='0'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_tilt_up(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    pan_px = int(h * 0.08)
    return (
        f"scale={w}:{h + pan_px},"
        f"zoompan=z='1':x='0':y='{pan_px}-(on/{frames}*{pan_px})'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_tilt_down(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    pan_px = int(h * 0.08)
    return (
        f"scale={w}:{h + pan_px},"
        f"zoompan=z='1':x='0':y='on/{frames}*{pan_px}'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_ken_burns_diagonal(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='min(zoom+0.0008\\,1.10)'"
        f":x='on/{frames}*(iw-iw/zoom)'"
        f":y='on/{frames}*(ih-ih/zoom)'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_whip_pan(duration: float, w: int, h: int, fps: int = 30) -> str:
    # Simulasi whip pan: zoom sedikit lalu pan cepat di akhir
    frames = max(1, int(duration * fps))
    return (
        f"scale=8000:-1,"
        f"zoompan=z='1.05'"
        f":x='if(gte(on\\,{int(frames*0.7)})\\,"
        f"(on-{int(frames*0.7)})/({frames}-{int(frames*0.7)})*(iw-iw/zoom)\\,0)'"
        f":y='ih/2-ih/zoom/2'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_handheld_shake(duration: float, w: int, h: int, fps: int = 30) -> str:
    # Shake ringan menggunakan crop bergerak; FFmpeg tidak punya random per-frame
    # pakai sin/cos kecil sebagai substitusi deterministik
    frames = max(1, int(duration * fps))
    amp = max(4, int(w * 0.008))
    return (
        f"scale={w + amp*2}:{h + amp*2},"
        f"crop={w}:{h}:"
        f"'(in_w-out_w)/2+{amp}*sin(n/3)':"
        f"'(in_h-out_h)/2+{amp}*cos(n/2)'"
    )


def effect_slow_zoom_punch(duration: float, w: int, h: int, fps: int = 30) -> str:
    frames = max(1, int(duration * fps))
    punch_start = int(frames * 0.80)
    return (
        f"scale=8000:-1,"
        f"zoompan=z='if(lte(on\\,{punch_start})\\,"
        f"1+0.05*(on/{punch_start})\\,"
        f"1.05+0.15*((on-{punch_start})/({frames}-{punch_start})))'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={w}x{h}:fps={fps}"
    )


def effect_static(duration: float, w: int, h: int, fps: int = 30) -> str:
    return f"scale={w}:{h},fps={fps}"


# ── Registry ──────────────────────────────────────────────────────────────────

EFFECT_MAP: dict[str, callable] = {
    "ken_burns_zoom_in":  effect_ken_burns_zoom_in,
    "ken_burns_zoom_out": effect_ken_burns_zoom_out,
    "slow_pan_left":      effect_slow_pan_left,
    "slow_pan_right":     effect_slow_pan_right,
    "tilt_up":            effect_tilt_up,
    "tilt_down":          effect_tilt_down,
    "ken_burns_diagonal": effect_ken_burns_diagonal,
    "whip_pan":           effect_whip_pan,
    "handheld_shake":     effect_handheld_shake,
    "slow_zoom_punch":    effect_slow_zoom_punch,
    "static":             effect_static,
}


def get_effect_filter(effect_name: str, duration: float, w: int, h: int, fps: int = 30) -> str:
    """Return FFmpeg vf filter string untuk satu efek."""
    fn = EFFECT_MAP.get(effect_name, effect_static)
    return fn(duration, w, h, fps)


# ══════════════════════════════════════════════════════════════════════════════
#  COLOR GRADES — FFmpeg curves filter
# ══════════════════════════════════════════════════════════════════════════════

_GRADE_FILTERS: dict[str, str] = {
    "cinematic_warm": (
        "curves=r='0/8 128/138 255/252':"
        "g='0/4 128/128 255/248':"
        "b='0/0 128/118 255/240'"
    ),
    "cinematic_cool": (
        "curves=r='0/2 128/119 255/245':"
        "g='0/4 128/125 255/248':"
        "b='0/10 128/138 255/255'"
    ),
    "moody_dark": (
        "curves=r='0/0 128/112 255/235':"
        "g='0/0 128/108 255/230':"
        "b='0/5 128/115 255/238'"
    ),
    "neutral": "",
    "vintage": (
        "curves=r='0/15 128/140 255/240':"
        "g='0/10 128/134 255/245':"
        "b='0/0 128/108 255/220'"
    ),
    "teal_orange": (
        "curves=r='0/0 128/140 255/255':"
        "g='0/5 128/128 255/250':"
        "b='0/20 128/115 255/255'"
    ),
    "black_white": "hue=s=0",
    "vibrant": (
        "curves=r='0/0 128/140 255/255':"
        "g='0/0 128/140 255/255':"
        "b='0/0 128/140 255/255'"
    ),
}


def get_grade_filter(grade_name: str) -> str:
    """
    Return FFmpeg vf filter string untuk color grade.

    Catatan:
    Color grading sengaja dimatikan (return kosong) agar pipeline render
    lebih ringan dan tidak memicu error filter curves pada beberapa environment.
    """
    _ = grade_name
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  TRANSITIONS — fade in/out sebagai drawbox atau format overlay
#  Dikembalikan sebagai (fade_in_filter, fade_out_filter) string
# ══════════════════════════════════════════════════════════════════════════════

def get_transition_filters(
    transition_in: str,
    transition_out: str,
    duration: float,
    fps: int = 30,
) -> tuple[str, str]:
    """
    Return (vf_in_filter, vf_out_filter).
    Kedua filter ini digabung ke filtergraph satu segmen.
    """
    fade_dur = min(0.4, duration * 0.2)
    fade_frames = max(1, int(fade_dur * fps))
    total_frames = max(1, int(duration * fps))
    out_start = max(0, total_frames - fade_frames)

    _FADE_IN = {
        "fade":         f"fade=t=in:st=0:d={fade_dur}",
        "crossdissolve": f"fade=t=in:st=0:d={fade_dur}",
        "dip_to_white": f"fade=t=in:st=0:d={fade_dur}:color=white",
        "glitch":       f"fade=t=in:st=0:d={fade_dur}",
        "wipe_left":    f"fade=t=in:st=0:d={fade_dur}",
        "cut":          "",
        "zoom_blur":    "",
    }
    _FADE_OUT = {
        "fade":         f"fade=t=out:st={out_start/fps:.3f}:d={fade_dur}",
        "crossdissolve": f"fade=t=out:st={out_start/fps:.3f}:d={fade_dur}",
        "dip_to_white": f"fade=t=out:st={out_start/fps:.3f}:d={fade_dur}:color=white",
        "zoom_blur":    f"fade=t=out:st={out_start/fps:.3f}:d={fade_dur}",
        "cut":          "",
        "glitch":       "",
        "wipe_left":    "",
    }

    return (
        _FADE_IN.get(transition_in, ""),
        _FADE_OUT.get(transition_out, ""),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY SHIM — agar kode lama yang masih import apply_effect/apply_grade
#  tidak langsung crash. Preview render masih pakai MoviePy path.
# ══════════════════════════════════════════════════════════════════════════════

def apply_effect(clip, effect_name: str):
    """Legacy shim: dipakai oleh preview render (MoviePy path)."""
    return clip  # preview pakai simplify_visuals=True, efek dilewati


def apply_grade(clip, grade_name: str):
    """Legacy shim: dipakai oleh preview render (MoviePy path)."""
    return clip


def apply_transitions(clip, transition_in: str, transition_out: str):
    """Legacy shim: dipakai oleh preview render (MoviePy path)."""
    from core.moviepy_compat import patch_moviepy
    patch_moviepy()
    dur = float(getattr(clip, "duration", 0) or 0)
    fade = min(0.25, dur * 0.15)
    if fade > 0.05:
        try:
            clip = clip.fadein(fade).fadeout(fade)
        except Exception:
            pass
    return clip
