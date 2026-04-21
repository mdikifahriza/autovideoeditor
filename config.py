# ─────────────────────────────────────────────
#  config.py  —  Konstanta Global (non-sensitif)
# ─────────────────────────────────────────────
"""
API key dan pengaturan kini dikelola oleh core/settings_manager.py
dan disimpan aman di AppData.
File ini hanya berisi konstanta statis yang tidak sensitif.
"""

from core.settings_manager import settings

# ── API Keys (dibaca dari settings aman) ─────
GEMINI_API_KEY   = settings.get("gemini_api_key",  "")
PEXELS_API_KEY   = settings.get("pexels_api_key",  "")
PIXABAY_API_KEY  = settings.get("pixabay_api_key", "")

# ── Gemini Model ─────────────────────────────
GEMINI_MODEL_TEXT   = settings.get("gemini_model_text",   "gemini-2.5-flash")
GEMINI_MODEL_VISION = settings.get("gemini_model_vision", "gemini-2.5-flash")

# ── Segmen Durasi (detik) ────────────────────
SEG_MIN   = settings.get("seg_min",   4)
SEG_MAX   = settings.get("seg_max",   12)
SEG_IDEAL = settings.get("seg_ideal", 6)

# ── B-roll ───────────────────────────────────
BROLL_CANDIDATES = settings.get("broll_candidates", 5)
BROLL_CACHE_DIR  = "broll_cache"

# ── Output Video ─────────────────────────────
OUTPUT_WIDTH   = settings.get("output_width",   1920)
OUTPUT_HEIGHT  = settings.get("output_height",  1080)
OUTPUT_FPS     = settings.get("output_fps",     30)
OUTPUT_BITRATE = settings.get("output_bitrate", "8000k")
OUTPUT_PRESET  = settings.get("output_preset",  "medium")

# ── Efek yang tersedia ───────────────────────
AVAILABLE_EFFECTS = [
    "ken_burns_zoom_in",
    "ken_burns_zoom_out",
    "slow_pan_left",
    "slow_pan_right",
    "static",
    "whip_pan", 
    "tilt_up", 
    "tilt_down",
    "ken_burns_diagonal", 
    "handheld_shake", 
    "slow_zoom_punch",
]

# ── Transisi yang tersedia ───────────────────
AVAILABLE_TRANSITIONS = [
    "fade",
    "crossdissolve",
    "cut",
    "wipe_left", 
    "dip_to_white", 
    "zoom_blur", 
    "glitch",
]

# ── Color grade yang tersedia ────────────────
AVAILABLE_GRADES = [
    "cinematic_warm",
    "cinematic_cool",
    "neutral",
    "moody_dark",
    "vintage", 
    "teal_orange", 
    "black_white", 
    "vibrant",
]

# ── Emphasis text style ──────────────────────
EMPHASIS_FONT_SIZE    = 58
EMPHASIS_FONT_COLOR   = "white"
EMPHASIS_STROKE_COLOR = "black"
EMPHASIS_STROKE_WIDTH = 2
EMPHASIS_ACCENT_COLOR = (255, 255, 255)
EMPHASIS_BG_ALPHA     = 0.0
FLOATING_TEXT_DEFAULT_FONT = "Segoe UI"
FLOATING_TEXT_DEFAULT_SIZE = 58
FLOATING_TEXT_DEFAULT_ANIMATION = "slide_up"
FLOATING_TEXT_DEFAULT_POSITION = "upper_third"
